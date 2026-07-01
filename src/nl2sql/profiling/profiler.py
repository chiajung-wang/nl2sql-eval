"""Deterministic per-column data profiling (Step 12, #140).

The deterministic half of the paper's metadata pipeline (arXiv:2505.19988v2 §2.1):
read each column's data and record its *shape* — counts, NULL/non-NULL, distinct
count, value min/max, string-length range, character class, longest common prefix,
and the top-k most frequent values. No LLM, no network beyond the SQLAlchemy
executor (CLAUDE.md §2); BIRD/SQLite is the path, and every statistic is computed
with a bounded query so profiling a wide table stays cheap.

The profile is the input to two things: the mechanical English rendering
(:mod:`nl2sql.profiling.render`) that becomes LLM-summarization context, and — the
raw stats — ``issue-4``'s value index. So the profiling pass is kept reusable and
value-only: it holds statistics, never opinions (the *meaning* is the LLM's job,
downstream and offline). Any per-column failure degrades to a minimal profile
rather than raising, so profiling a messy real db never crashes the precompute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

# How many distinct top values (with counts) to keep per column — enough to expose
# an enum or a dominant-value skew without dumping a high-cardinality column.
DEFAULT_TOP_K = 5
# Bound the value sample pulled for the in-Python shape stats (char class, common
# prefix); a column's format is evident from a modest sample, and the cap keeps the
# profiler cheap on large tables.
DEFAULT_SAMPLE_LIMIT = 200


class CharClass(StrEnum):
    """The character class of a column's (string-coerced) values — a format signal.

    Deterministic and coarse on purpose: it feeds the *mechanical* English, which
    the LLM summarizer then interprets ("14-char digit string" → "a school id").
    """

    EMPTY = "empty"  # no non-null values sampled
    DIGITS = "digits"  # all values are [0-9]+
    ALPHA = "alpha"  # all values are [A-Za-z]+
    ALNUM = "alnum"  # all values are alphanumeric (no spaces/punctuation)
    MIXED = "mixed"  # anything else (spaces, punctuation, symbols)


@dataclass(frozen=True)
class ColumnProfile:
    """The deterministic profile of one column — statistics only, no interpretation.

    ``min_value``/``max_value`` are the value extremes (as strings, so numeric and
    text columns share one shape); ``min_len``/``max_len`` are the string-length
    range. ``common_prefix`` is the longest prefix shared by every sampled value
    (empty when they diverge). ``top_values`` are ``(value, count)`` pairs, most
    frequent first. ``is_unique`` when distinct == non-null (a candidate key).
    """

    table: str
    name: str
    declared_type: str
    row_count: int
    non_null_count: int
    distinct_count: int
    char_class: CharClass = CharClass.EMPTY
    min_value: str | None = None
    max_value: str | None = None
    min_len: int | None = None
    max_len: int | None = None
    common_prefix: str = ""
    top_values: tuple[tuple[str, int], ...] = ()

    @property
    def null_count(self) -> int:
        return self.row_count - self.non_null_count

    @property
    def null_fraction(self) -> float:
        return self.null_count / self.row_count if self.row_count else 0.0

    @property
    def is_unique(self) -> bool:
        """Distinct equals non-null (and there is data): a candidate key/id column."""
        return self.non_null_count > 0 and self.distinct_count == self.non_null_count

    @property
    def is_constant_length(self) -> bool:
        """Every non-null value has the same length — a fixed-width code signal."""
        return (
            self.min_len is not None
            and self.max_len is not None
            and self.min_len == self.max_len
        )


@dataclass(frozen=True)
class TableProfile:
    """One table's per-column profiles, in column declaration order."""

    name: str
    row_count: int
    columns: tuple[ColumnProfile, ...] = ()


@dataclass(frozen=True)
class DbProfile:
    """A whole db's table profiles, keyed by table name (declaration order)."""

    db_id: str
    tables: tuple[TableProfile, ...] = field(default_factory=tuple)

    def by_name(self) -> dict[str, TableProfile]:
        return {t.name: t for t in self.tables}


def _char_class(values: list[str]) -> CharClass:
    """The coarsest character class covering every value (deterministic)."""
    if not values:
        return CharClass.EMPTY
    if all(v.isdigit() for v in values):
        return CharClass.DIGITS
    if all(v.isalpha() for v in values):
        return CharClass.ALPHA
    if all(v.isalnum() for v in values):
        return CharClass.ALNUM
    return CharClass.MIXED


def _common_prefix(values: list[str]) -> str:
    """Longest string prefix shared by every value ('' when they diverge)."""
    if not values:
        return ""
    prefix = values[0]
    for v in values[1:]:
        while not v.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def _scalar(conn: Connection, sql: str, table: str, column: str) -> object:
    """Run a one-value aggregate, quoting identifiers; ``None`` on any failure."""
    try:
        return conn.execute(
            text(sql.format(col=f'"{column}"', tbl=f'"{table}"'))
        ).scalar()
    except Exception:
        return None


def profile_column(
    conn: Connection,
    table: str,
    column: str,
    declared_type: str,
    row_count: int,
    *,
    top_k: int = DEFAULT_TOP_K,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    redact: bool = False,
) -> ColumnProfile:
    """Profile one column via bounded aggregate + sample queries.

    Counts (non-null, distinct), value extremes, and length range come from cheap
    SQL aggregates; the character class and common prefix are computed in Python
    over a bounded distinct-value sample. ``top_values`` is a ``GROUP BY … ORDER BY
    COUNT DESC`` — the enum/skew signal. Every read degrades to a null/empty result
    rather than raising, so a single unreadable column never fails the precompute.

    ``redact`` (for a PII column, per the db's redaction policy) suppresses the
    **value-bearing** fields — ``min_value``/``max_value``/``common_prefix``/
    ``top_values`` — so a raw value can never reach the committed artifact, the
    generate prompt, or a trace (CLAUDE.md §5.3). The *shape-only* stats (counts,
    distinct, NULL, length range, character class) are kept: they describe the
    column without revealing any value. On BIRD (public data, no policy) nothing is
    redacted, so this is a no-op there.
    """
    non_null = _scalar(conn, "SELECT COUNT({col}) FROM {tbl}", table, column)
    distinct = _scalar(conn, "SELECT COUNT(DISTINCT {col}) FROM {tbl}", table, column)

    sample: list[str] = []
    try:
        rows = conn.execute(
            text(
                f'SELECT DISTINCT "{column}" FROM "{table}" '
                f'WHERE "{column}" IS NOT NULL LIMIT :n'
            ),
            {"n": sample_limit},
        ).fetchall()
        sample = [str(v) for (v,) in rows if v is not None]
    except Exception:
        sample = []

    lengths = [len(v) for v in sample]
    # Shape-only stats are always safe (they reveal no value). Value-bearing
    # extremes / prefix / top values are computed only for a non-redacted column.
    if redact:
        return ColumnProfile(
            table=table,
            name=column,
            declared_type=declared_type,
            row_count=row_count,
            non_null_count=int(non_null or 0),
            distinct_count=int(distinct or 0),
            char_class=_char_class(sample),
            min_len=min(lengths) if lengths else None,
            max_len=max(lengths) if lengths else None,
        )

    min_value = _scalar(conn, "SELECT MIN({col}) FROM {tbl}", table, column)
    max_value = _scalar(conn, "SELECT MAX({col}) FROM {tbl}", table, column)
    top_values: tuple[tuple[str, int], ...] = ()
    if top_k > 0:
        try:
            rows = conn.execute(
                text(
                    f'SELECT "{column}", COUNT(*) AS n FROM "{table}" '
                    f'WHERE "{column}" IS NOT NULL '
                    f'GROUP BY "{column}" ORDER BY n DESC, "{column}" LIMIT :k'
                ),
                {"k": top_k},
            ).fetchall()
            top_values = tuple((str(v), int(n)) for v, n in rows)
        except Exception:
            top_values = ()

    return ColumnProfile(
        table=table,
        name=column,
        declared_type=declared_type,
        row_count=row_count,
        non_null_count=int(non_null or 0),
        distinct_count=int(distinct or 0),
        char_class=_char_class(sample),
        min_value=None if min_value is None else str(min_value),
        max_value=None if max_value is None else str(max_value),
        min_len=min(lengths) if lengths else None,
        max_len=max(lengths) if lengths else None,
        common_prefix=_common_prefix(sample),
        top_values=top_values,
    )


def profile_table(
    conn: Connection,
    table: str,
    columns: list[tuple[str, str]],
    *,
    top_k: int = DEFAULT_TOP_K,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    redact_columns: frozenset[str] = frozenset(),
) -> TableProfile:
    """Profile every column of ``table``; ``columns`` is ``(name, declared_type)``.

    ``redact_columns`` is a set of casefolded ``"table.column"`` keys (the db's PII
    columns); a matching column is profiled shape-only (no raw values) — see
    :func:`profile_column`.
    """
    row_count = int(_scalar(conn, "SELECT COUNT(*) FROM {tbl}", table, "*") or 0)
    profiles = tuple(
        profile_column(
            conn,
            table,
            name,
            dtype,
            row_count,
            top_k=top_k,
            sample_limit=sample_limit,
            redact=f"{table.casefold()}.{name.casefold()}" in redact_columns,
        )
        for name, dtype in columns
    )
    return TableProfile(name=table, row_count=row_count, columns=profiles)


def profile_db(
    engine: Engine,
    db_id: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    redact_columns: frozenset[str] = frozenset(),
) -> DbProfile:
    """Profile every table of ``engine`` (read-only) into a :class:`DbProfile`.

    Tables and columns come from SQLAlchemy's ``Inspector`` (portable across the
    BIRD/SQLite and payments/Postgres paths), sorted by name so the profile — and
    any artifact derived from it — is stable across runs.

    ``redact_columns`` (casefolded ``"table.column"`` keys — the db's PII columns
    from its redaction policy) forces those columns to profile **shape-only**, so no
    raw value is ever persisted or rendered into a prompt (CLAUDE.md §5.3). On the
    BIRD path (public data, no policy) it defaults to empty — a no-op.
    """
    inspector = inspect(engine)
    tables: list[TableProfile] = []
    with engine.connect() as conn:
        for name in sorted(inspector.get_table_names()):
            columns = [
                (col["name"], str(col.get("type", "")).strip())
                for col in inspector.get_columns(name)
            ]
            tables.append(
                profile_table(
                    conn,
                    name,
                    columns,
                    top_k=top_k,
                    sample_limit=sample_limit,
                    redact_columns=redact_columns,
                )
            )
    return DbProfile(db_id=db_id, tables=tuple(tables))
