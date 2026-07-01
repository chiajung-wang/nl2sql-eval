"""Retrievable schema-metadata store + deterministic lexical retrieval.

Backs schema-RAG (Step 6). Introspect each table's columns/types, foreign keys,
and **a few sample values per column** — knowing ``status ∈ {failed, settled}``
changes the SQL — then score tables against a question by lexical token overlap
so ``generate`` sees only the **relevant** tables instead of the full schema
dump (the Step-3 naive baseline).

Deterministic and offline by design: no embeddings, no network, no LLM — lexical
overlap over name/column/sample-value tokens. (sqlglot is the tool for SQL
*semantics* elsewhere; this is metadata introspection, not SQL parsing.) Portable
across the SQLite (BIRD) and Postgres (payments) paths via SQLAlchemy's
``Inspector``, so the harness and the demo build the index the same way.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

# A handful of distinct sample values per column — enough to surface enum-like
# signal (status, type, country codes) without dumping high-cardinality noise.
DEFAULT_SAMPLE_VALUES = 5
# Pull a few more *distinct* values than we keep, so dropping over-long ones still
# leaves enough short, enum-like samples — and so a bounded ``SELECT DISTINCT``
# stays cheap (it stops as soon as this many distinct values are found, which is
# immediate for a low-cardinality enum and naturally capped for a wide column).
SAMPLE_OVERSAMPLE = 4
# Skip free-text/blob-ish values: long strings are noise for lexical matching.
MAX_SAMPLE_LEN = 40

# Default breadth of a retrieval: the top-scoring tables (plus their FK
# neighbours) handed to the generator. Wide enough for multi-join questions,
# narrow enough to beat the full dump on large schemas.
DEFAULT_MAX_TABLES = 8

# A table/column-name hit is a stronger relevance signal than a sample-value hit
# (a question naming "customers" is surer than one merely mentioning a value that
# happens to appear in some column).
NAME_WEIGHT = 3
SAMPLE_WEIGHT = 1

# Heuristic chars-per-token for the schema-token budget (Step-6 follow-up, #75).
# A budget is a *cost/latency policy* on how much schema rides in the prompt — not
# the model's context limit (BIRD schemas all fit that). The estimate need only be
# monotonic and stable, so the ~4-chars/token rule of thumb is enough; we never
# call a tokenizer (offline, deterministic, no provider dependency — PRD §5
# heuristic-first). It is the same lever the adaptive gate (#76) will switch on.
CHARS_PER_TOKEN = 4

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def estimate_tokens(text: str) -> int:
    """Heuristic token count for ``text`` — ``ceil(len / CHARS_PER_TOKEN)``.

    Deterministic and provider-free (no tokenizer call): the schema-token budget
    only needs a stable, monotonic size proxy to rank "does this fit?" decisions,
    not exact provider token counts. Empty text is 0 tokens.
    """
    return -(-len(text) // CHARS_PER_TOKEN)  # ceil division


def _tokens(s: str) -> set[str]:
    """Lowercase alphanumeric tokens, splitting snake_case and camelCase.

    ``customerId`` and ``customer_id`` both yield ``{customer, id}`` so a
    question's words line up with column names regardless of naming style.
    """
    return set(_TOKEN_RE.findall(_CAMEL_RE.sub(" ", s).lower()))


@dataclass(frozen=True)
class ColumnMeta:
    """One column's name, declared type, sample values, and optional description.

    ``description`` is the metadata-source gloss (Step 12, #140): supplied,
    profiling-derived, or fused, chosen when the index is built. It rides into the
    rendered schema the generator sees — **prompt content only**, never read by the
    guard or comparator (those stay data-independent). Empty by default (the
    supplied-only current behaviour, when no metadata is selected).
    """

    name: str
    type: str
    sample_values: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class TableMeta:
    """One table's columns, foreign keys, and optional short description.

    ``foreign_keys`` is ``(local_column, referred_table)`` pairs — enough to pull
    a selected table's join neighbours into the retrieval and to print the join
    edges in the rendered block.
    """

    name: str
    columns: tuple[ColumnMeta, ...]
    foreign_keys: tuple[tuple[str, str], ...] = ()
    description: str = ""

    def name_tokens(self) -> set[str]:
        """Tokens from the table name, its column names, and its description."""
        toks = _tokens(self.name) | _tokens(self.description)
        for c in self.columns:
            toks |= _tokens(c.name)
        return toks

    def sample_tokens(self) -> set[str]:
        """Tokens drawn from the column sample values (the ``settled``/``failed``
        signal)."""
        toks: set[str] = set()
        for c in self.columns:
            for v in c.sample_values:
                toks |= _tokens(v)
        return toks

    def render(self) -> str:
        """A prompt-ready block: ``CREATE TABLE`` + FK edges + sample values.

        Rendered from introspected metadata (not raw DDL) so it is identical on
        SQLite and Postgres, and so sample values — which the naive dump lacked —
        ride along with the schema the generator sees.
        """
        col_lines = []
        for c in self.columns:
            # A field description (supplied/profiling/fused, #140) rides as a leading
            # comment line above the column — prompt content the generator reads. A
            # leading (not trailing) comment keeps the column commas intact.
            gloss = f"  -- {c.description}\n" if c.description else ""
            col_lines.append(gloss + f"  {c.name} {c.type}".rstrip())
        col_lines += [
            f"  FOREIGN KEY ({local}) REFERENCES {referred}"
            for local, referred in self.foreign_keys
        ]
        block = f"CREATE TABLE {self.name} (\n" + ",\n".join(col_lines) + "\n);"
        if self.description:
            block = f"-- {self.description}\n{block}"
        samples = [
            f"--   {c.name} ∈ {{{', '.join(c.sample_values)}}}"
            for c in self.columns
            if c.sample_values
        ]
        if samples:
            block += "\n-- sample values:\n" + "\n".join(samples)
        return block


@dataclass(frozen=True)
class SchemaIndex:
    """A db's tables as retrievable metadata, in declaration order.

    The retriever scores tables against a question lexically and renders only the
    selected ones; with no lexical signal it falls back to the whole schema (never
    worse than the naive dump). Empty-retrieval handling as a terminal state lands
    with the loop-aware re-trigger in the next slice.
    """

    tables: tuple[TableMeta, ...]

    def by_name(self) -> dict[str, TableMeta]:
        return {t.name: t for t in self.tables}

    def score(self, question: str) -> dict[str, int]:
        """Lexical relevance score per table (name hits weigh more than samples)."""
        q = _tokens(question)
        return {
            t.name: NAME_WEIGHT * len(q & t.name_tokens())
            + SAMPLE_WEIGHT * len(q & t.sample_tokens())
            for t in self.tables
        }

    def relevant_tables(
        self,
        question: str,
        *,
        max_tables: int = DEFAULT_MAX_TABLES,
        expand_fks: bool = True,
        floor: int = 0,
    ) -> list[str]:
        """The relevant table names for ``question``, in declaration order.

        Top ``max_tables`` by score (ties broken by name for determinism), then —
        because join questions need the tables on the *other* side of a key —
        each selected table's FK-referenced tables are pulled in. The whole set is
        then capped at ``max_tables`` with **ranked picks keeping priority over FK
        neighbours**, so a fan-out table can't re-inflate the retrieval toward the
        full dump on a wide schema.

        ``floor`` (the loop-aware re-retrieve lever, issue #46) guarantees *at
        least* that many tables, padding from declaration order beyond the lexical
        picks — a widened re-retrieve surfaces more schema than the first attempt,
        and a large enough floor reaches the full dump. With no table scoring above
        zero and no floor, returns every table (degrade to the full dump rather
        than starve the generator).
        """
        scores = self.score(question)
        ranked = [
            name
            for name, s in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            if s > 0
        ]
        if not ranked and floor <= 0:
            return [t.name for t in self.tables]
        # Ranked picks first (priority), then FK neighbours fill any budget left.
        selected = ranked[:max_tables]
        if expand_fks:
            by_name = self.by_name()
            chosen = set(selected)
            for name in list(selected):
                for _local, referred in by_name[name].foreign_keys:
                    if referred in by_name and referred not in chosen:
                        chosen.add(referred)
                        selected.append(referred)
        selected = selected[:max_tables]
        # Widen to the floor: pad with not-yet-chosen tables in declaration order.
        if floor > len(selected):
            chosen = set(selected)
            for t in self.tables:
                if len(selected) >= floor:
                    break
                if t.name not in chosen:
                    selected.append(t.name)
                    chosen.add(t.name)
        order = {t.name: i for i, t in enumerate(self.tables)}
        return sorted(selected, key=lambda n: order[n])

    def render(self, table_names: Sequence[str]) -> str:
        """Render the given tables' blocks as the focused schema for the prompt."""
        by_name = self.by_name()
        return "\n\n".join(by_name[n].render() for n in table_names if n in by_name)

    def render_tokens(self, table_names: Sequence[str]) -> int:
        """Estimated token size of the rendered block for ``table_names``."""
        return estimate_tokens(self.render(table_names))

    def ranked_names(self, question: str) -> list[str]:
        """**All** table names in relevance order for ``question``.

        Score-descending, ties broken by declaration order (stable, deterministic).
        Unlike :meth:`relevant_tables` this never truncates — it is the priority
        order a *budget* then fills (the budget, not a table cap, decides how many
        fit). The naive-truncation baseline uses plain declaration order instead;
        the only difference between the two budget modes (#75) is this ordering.
        """
        scores = self.score(question)
        order = {t.name: i for i, t in enumerate(self.tables)}
        return sorted(
            (t.name for t in self.tables), key=lambda n: (-scores[n], order[n])
        )

    def fit_budget(self, ordered_names: Sequence[str], budget_tokens: int) -> list[str]:
        """Greedy prefix of ``ordered_names`` whose rendered size fits the budget.

        Walks ``ordered_names`` in priority order and keeps each table while the
        running rendered-token total stays within ``budget_tokens``; once a table
        would bust the budget the walk **stops** (truncation semantics, not bin
        packing — so a tight budget yields a clean priority prefix). At least the
        first table is always kept, so the generator never sees an empty schema
        even when one table alone exceeds the budget. The kept set is returned in
        **declaration order** (the canonical render order), so only *which* tables
        differ between modes, never the rendering. Unknown names are ignored.
        """
        by_name = self.by_name()
        kept: list[str] = []
        used = 0
        for name in ordered_names:
            meta = by_name.get(name)
            if meta is None:
                continue
            cost = estimate_tokens(meta.render())
            if kept and used + cost > budget_tokens:
                break
            kept.append(name)
            used += cost
        order = {t.name: i for i, t in enumerate(self.tables)}
        return sorted(kept, key=lambda n: order[n])


def _sample_values(
    conn: Connection, table: str, column: str, limit: int
) -> tuple[str, ...]:
    """Up to ``limit`` distinct, short sample values from a column.

    Uses a bounded ``SELECT DISTINCT … LIMIT`` so a low-cardinality enum is
    captured **wherever its values sit** in the table — not just within an
    arbitrary row prefix (a second enum value buried past row N would otherwise be
    missed, breaking the ``status ∈ {failed, settled}`` signal). The DB stops once
    it has found enough distinct values, so this stays cheap on big tables. Over-
    long (free-text/blob) values are dropped; the result is sorted for a
    deterministic index. Any failure degrades to no samples, never raising.
    """
    if limit <= 0:
        return ()
    try:
        rows = conn.execute(
            text(
                f'SELECT DISTINCT "{column}" FROM "{table}" '
                f'WHERE "{column}" IS NOT NULL LIMIT :n'
            ),
            {"n": limit * SAMPLE_OVERSAMPLE},
        ).fetchall()
    except Exception:
        return ()
    short = [s for (value,) in rows if (s := str(value)) and len(s) <= MAX_SAMPLE_LEN]
    # Already distinct from SQL; dedup defensively after str() coercion.
    return tuple(sorted(dict.fromkeys(short))[:limit])


def build_schema_index(
    engine: Engine,
    *,
    sample_values: int = DEFAULT_SAMPLE_VALUES,
    descriptions: dict[str, str] | None = None,
    column_descriptions: dict[str, str] | None = None,
) -> SchemaIndex:
    """Introspect ``engine`` into a :class:`SchemaIndex` (read-only).

    Tables and columns come from SQLAlchemy's ``Inspector`` (portable across the
    BIRD/SQLite and payments/Postgres paths); sample values from a bounded SELECT
    per column. ``descriptions`` optionally supplies a short per-table gloss.
    ``column_descriptions`` is the Step-12 #140 metadata-source selection — per-column
    glosses keyed ``"table.column"`` (casefolded), already merged for the chosen
    source (supplied / profiling / fused) — that ride into the rendered schema.
    Tables are sorted by name so the index — and any prompt rendered from it — is
    stable across runs.
    """
    inspector = inspect(engine)
    descriptions = descriptions or {}
    column_descriptions = column_descriptions or {}
    tables: list[TableMeta] = []
    with engine.connect() as conn:
        for name in sorted(inspector.get_table_names()):
            columns = tuple(
                ColumnMeta(
                    col["name"],
                    str(col.get("type", "")).strip(),
                    _sample_values(conn, name, col["name"], sample_values),
                    column_descriptions.get(
                        f"{name.casefold()}.{col['name'].casefold()}", ""
                    ),
                )
                for col in inspector.get_columns(name)
            )
            fks = tuple(
                (fk["constrained_columns"][0], fk["referred_table"])
                for fk in inspector.get_foreign_keys(name)
                if fk.get("referred_table") and fk.get("constrained_columns")
            )
            tables.append(TableMeta(name, columns, fks, descriptions.get(name, "")))
    return SchemaIndex(tuple(tables))
