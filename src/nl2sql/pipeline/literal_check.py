"""Stage: literal_check — literal→field steering (Step 12, #141).

Source: Shkapenyuk et al., arXiv:2505.19988v2 §3. Targets the **right value, wrong
column** wrong-answer class (the ``ambiguous_column`` root cause #134 labels): the
generator constrains a literal against a plausible-but-wrong field. After
generation, this checks — **mechanically** — whether each string literal in the
candidate actually occurs in the column it is constrained against (per the sampled
:class:`~nl2sql.value_index.ValueIndex`); if not, and the literal *does* occur in
other columns, it feeds a **steering correction** naming those columns, exactly as
the paper flips a ``County Name`` constraint to the correct ``District`` field.

Determinism boundary (CLAUDE.md §4/§7): literal extraction is **sqlglot-AST** (never
a regex over SQL) and the index lookup is a mechanical set membership — no LLM in the
decision. Only the *rephrase* is a model call, and it rides the existing
``correct.py`` loop within the capped retry budget. Like the soundness stage (#139),
a hit is a **correction signal, never a hard reject** — a false steer (a sampling
miss) costs at most a wasted retry, never a dropped run, so the check only fires when
it is *confident*: the constrained column was sampled and lacks the literal, and some
other sampled column has it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from nl2sql.obs import stage_span
from nl2sql.pipeline.generate import DEFAULT_DIALECT
from nl2sql.pipeline.state import RunState
from nl2sql.value_index import ValueIndex

logger = logging.getLogger(__name__)

_LITERAL_DIALECTS: tuple[str | None, ...] = ("sqlite", None)


@dataclass(frozen=True)
class LiteralFinding:
    """One off-column literal: the value, the column it was constrained against (as
    written), and the columns whose sample *does* contain it."""

    literal: str
    constrained_column: str
    candidate_columns: tuple[str, ...]


def _parse(sql: str, dialect: str) -> exp.Expression | None:
    """Parse one statement (named dialect then generic); ``None`` if neither works."""
    normalized = _normalize_dialect(dialect)
    attempts = _LITERAL_DIALECTS if normalized is None else (normalized, None)
    for parse_dialect in attempts:
        try:
            tree = sqlglot.parse_one(sql, dialect=parse_dialect)
        except (ParseError, TokenError):
            continue
        if tree is not None:
            return tree
    return None


def _normalize_dialect(dialect: str) -> str | None:
    aliases = {
        "postgresql": "postgres",
        "postgres": "postgres",
        "sqlite": "sqlite",
        "mysql": "mysql",
        "bigquery": "bigquery",
    }
    return aliases.get(dialect.strip().lower())


def _alias_to_table(tree: exp.Expression) -> dict[str, str]:
    """Map every table alias (and each real table name to itself), casefolded.

    So ``FROM schools AS s`` lets a ``s.col`` reference resolve to ``schools.col``;
    an unqualified real table name resolves to itself."""
    mapping: dict[str, str] = {}
    for tbl in tree.find_all(exp.Table):
        name = tbl.name.casefold()
        if not name:
            continue
        mapping[name] = name
        alias = tbl.alias
        if alias:
            mapping[alias.casefold()] = name
    return mapping


def _query_tables(tree: exp.Expression) -> set[str]:
    """The real base-table names the query references, casefolded (CTEs excluded)."""
    cte_names = {c.alias_or_name.casefold() for c in tree.find_all(exp.CTE)}
    return {
        t.name.casefold()
        for t in tree.find_all(exp.Table)
        if t.name and t.name.casefold() not in cte_names
    }


def _string_literal(node: exp.Expression | None) -> str | None:
    """The Python string of a string ``Literal`` node, else ``None``."""
    if isinstance(node, exp.Literal) and node.is_string:
        return node.this
    return None


def _bindings(tree: exp.Expression) -> list[tuple[exp.Column, str]]:
    """``(column, string-literal)`` pairs the query constrains via ``=`` or ``IN``.

    Only equality-shaped constraints — ``col = 'x'`` (either operand order) and
    ``col IN ('x', …)`` — bind a literal to a *specific* column, which is the shape
    the on-column check is meaningful for. Range/LIKE predicates are skipped."""
    pairs: list[tuple[exp.Column, str]] = []
    for eq in tree.find_all(exp.EQ):
        col = eq.this if isinstance(eq.this, exp.Column) else eq.expression
        lit_node = eq.expression if col is eq.this else eq.this
        literal = _string_literal(lit_node)
        if isinstance(col, exp.Column) and literal is not None:
            pairs.append((col, literal))
    for in_node in tree.find_all(exp.In):
        col = in_node.this
        if not isinstance(col, exp.Column):
            continue
        for item in in_node.expressions:
            literal = _string_literal(item)
            if literal is not None:
                pairs.append((col, literal))
    return pairs


def _constrained_keys(
    col: exp.Column, alias_map: dict[str, str], tables: set[str], index: ValueIndex
) -> list[str]:
    """The indexed ``table.column`` keys a bound column could refer to.

    A qualified ``t.c`` resolves its qualifier via the alias map; a bare ``c`` maps
    to every query table that has an indexed column named ``c``. Only keys the index
    actually sampled are returned — an unsampled column is "unknown", never steered.
    """
    column = col.name.casefold()
    qualifier = col.table.casefold() if col.table else ""
    if qualifier:
        real = alias_map.get(qualifier, qualifier)
        candidates = [f"{real}.{column}"]
    else:
        candidates = [f"{t}.{column}" for t in tables]
    return [k for k in candidates if index.is_indexed(k)]


def check_literals(
    sql: str | None, index: ValueIndex, *, dialect: str = DEFAULT_DIALECT
) -> list[LiteralFinding]:
    """Find literals constrained against a column whose sample lacks them.

    For each ``col = 'x'`` / ``col IN (…)`` binding: resolve the column to its
    indexed key(s); if **none** of them contains the literal but **other** columns
    do, emit a :class:`LiteralFinding`. Fires only when confident — the constrained
    column was sampled (so its absence is real, not "unknown") and a different column
    holds the value — so a sampling miss cannot spuriously steer an on-column literal.
    Returns an empty list on unparseable SQL or when no literal is off-column.
    """
    if not sql or not sql.strip():
        return []
    tree = _parse(sql, dialect)
    if tree is None:
        return []
    alias_map = _alias_to_table(tree)
    tables = _query_tables(tree)

    findings: list[LiteralFinding] = []
    seen: set[tuple[str, str]] = set()
    for col, literal in _bindings(tree):
        keys = _constrained_keys(col, alias_map, tables, index)
        if not keys:
            continue  # column not indexed → unknown, never steer
        if any(index.column_contains(k, literal) for k in keys):
            continue  # on-column — correct
        holders = index.columns_containing(literal)
        candidates = sorted(holders - set(keys))
        if not candidates:
            continue  # literal is nowhere we sampled — can't help, don't steer
        written = col.sql(dialect=_normalize_dialect(dialect) or None)
        dedup = (written, literal)
        if dedup in seen:
            continue
        seen.add(dedup)
        findings.append(
            LiteralFinding(
                literal=literal,
                constrained_column=written,
                candidate_columns=tuple(candidates),
            )
        )
    return findings


def steering_message(findings: Sequence[LiteralFinding]) -> str:
    """The correction text naming, per off-column literal, where the value occurs."""
    lines = [
        f"The value '{f.literal}' does not occur in {f.constrained_column}; "
        f"it occurs in {', '.join(f.candidate_columns)}. "
        f"Revise the query to constrain one of those columns instead."
        for f in findings
    ]
    return " ".join(lines)


def literal_check(
    state: RunState,
    index: ValueIndex | None,
    *,
    dialect: str = DEFAULT_DIALECT,
) -> RunState:
    """Pipeline stage: flag off-column literals in ``state.candidate_sql``.

    On a hit, sets ``state.literal_flag``/``literal_reason`` so the graph can feed the
    steering message back to ``generate`` within the retry budget (or, if the budget
    is spent, let the candidate execute anyway — a steering heuristic never loses a
    run). A no-op when no value index is configured. Fields are reset on every scan so
    a re-tried candidate is never judged by a stale flag. Only the flag/count (never
    values beyond the correction text) touch the obs span. Mutates and returns state.
    """
    with stage_span(
        "literal_check", db_id=state.db_id, attempt=state.attempts
    ) as extra:
        findings = (
            check_literals(state.candidate_sql, index, dialect=dialect)
            if index is not None
            else []
        )
        state.literal_flag = bool(findings)
        state.literal_reason = steering_message(findings) if findings else None
        extra["flagged"] = bool(findings)
        extra["n_findings"] = len(findings)
    return state
