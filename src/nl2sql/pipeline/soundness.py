"""Stage: soundness — deterministic "bad-construction" checks (Step 12, #139).

Source: Shkapenyuk et al., "Automatic Metadata Extraction for Text-to-SQL"
(arXiv:2505.19988v2, §4). Their BIRD submission runs a set of deterministic,
AST-detectable checks *after* generation and *before accepting* a candidate; on a
hit it asks the model to correct (within a capped retry budget). Each pattern
correlates with a **wrong answer**, not a style nit:

- **NULL-ordering hazard** — a ``NULL`` sorts before all values, so ``min(f)`` or
  ``ORDER BY f ASC LIMIT 1`` without a ``f IS NOT NULL`` guard silently returns a
  NULL-driven wrong answer.
- **min/max via a scalar subquery** where ``ORDER BY … LIMIT 1`` is the idiomatic,
  less error-prone form (diagnostic-grade).
- **String catenation of distinct fields** in the projection where the question
  wants the fields returned separately (a wrong *shape*).

**Relation to the guard (CLAUDE.md §4).** This is the *same shape* as ``guard.py``
— deterministic sqlglot-AST checks, no regex for SQL semantics, no LLM in the
detection — but a **different contract**. The guard's rules are *safety gates*: a
hit is a terminal ``GUARDRAIL_REJECTED``. A soundness hit is a **correction
signal**: with retry budget left the graph feeds the reason back to ``generate``
and tries again; with the budget spent the candidate proceeds to ``execute``
anyway. A soundness heuristic must never *lose* a run — a false positive degrades
to a wasted retry, not a dropped answer. So the default is feed-back, never
hard-reject.

The checks reuse :class:`nl2sql.pipeline.guard.GuardResult` (rule / reason / note)
purely for explainability; a soundness ``REJECT`` decision means "flagged for
correction", read by the graph, not by the terminal-state classifier as a
rejection. The detection is import-shared and offline-testable — it calls nothing
from ``eval/`` and needs no model — and is *measured* against
``fixtures/soundness/`` (catch rate + false-positive rate, PRD rule 11).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from nl2sql.obs import stage_span
from nl2sql.pipeline.generate import DEFAULT_DIALECT
from nl2sql.pipeline.guard import GuardDecision, GuardResult
from nl2sql.pipeline.state import RunState

logger = logging.getLogger(__name__)

# BIRD is SQLite; fall back to the generic parser so a candidate the named dialect
# can't parse still gets checked (mirrors guard's and the linker's tolerant parse).
_SOUNDNESS_DIALECTS: tuple[str | None, ...] = ("sqlite", None)


def _parse(sql: str, dialect: str | None) -> exp.Expression | None:
    """Parse one statement, named dialect then generic; ``None`` if neither works.

    Soundness runs *after* the guard has already proven the candidate parses and is
    a single safe statement, so an unparseable string here is not a soundness
    concern — it allows through (the guard owns parse-safety). Both sqlglot failure
    modes are swallowed so a malformed candidate never crashes the run."""
    attempts = _SOUNDNESS_DIALECTS if dialect is None else (dialect, None)
    for parse_dialect in attempts:
        try:
            tree = sqlglot.parse_one(sql, dialect=parse_dialect)
        except (ParseError, TokenError):
            continue
        if tree is not None:
            return tree
    return None


def _column_name(node: exp.Expression | None) -> str | None:
    """The casefolded column name a node refers to, or ``None`` if it isn't a plain
    column reference (a literal, an expression, a star, …)."""
    if isinstance(node, exp.Column):
        return node.name.casefold() or None
    return None


def _null_excluded_columns(select: exp.Select) -> set[str]:
    """Columns the WHERE clause constrains to be non-NULL.

    Two null-excluding shapes count, casefolded:

    - an explicit ``f IS NOT NULL`` (sqlglot: ``Not(Is(col, Null))``);
    - a comparison predicate on ``f`` (``f > 0``, ``f = x``, ``f BETWEEN …``,
      ``f IN (…)``) — SQL's three-valued logic drops NULLs from any such predicate,
      so the ascending-order / ``min`` hazard is already neutralized for ``f``.

    Deliberately generous (a superset of the strict ``IS NOT NULL``) to keep the
    false-positive rate low: a query that already filters ``f`` is not flagged.
    """
    where = select.args.get("where")
    if where is None:
        return set()
    guarded: set[str] = set()
    # Explicit  f IS NOT NULL  →  Not(Is(col, Null)).
    for is_node in where.find_all(exp.Is):
        if isinstance(is_node.expression, exp.Null) and isinstance(
            is_node.parent, exp.Not
        ):
            name = _column_name(is_node.this)
            if name:
                guarded.add(name)
    # Any comparison / range / membership predicate excludes NULLs for its column.
    predicate_types = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ, exp.NEQ, exp.Between)
    for pred in where.find_all(*predicate_types):
        for side in (pred.this, pred.args.get("expression")):
            name = _column_name(side)
            if name:
                guarded.add(name)
    for in_node in where.find_all(exp.In):
        name = _column_name(in_node.this)
        if name:
            guarded.add(name)
    return guarded


def _check_null_ordering(select: exp.Select) -> str | None:
    """Flag an ascending-order / ``min`` result that a NULL could silently win.

    Two hazard shapes, each only when the column is **not** already NULL-excluded
    by the WHERE clause (:func:`_null_excluded_columns`):

    - ``min(f)`` in the projection — ``MIN`` ignores NULLs in *aggregation*, but the
      paper's hazard is the row-selecting idiom; we flag the bare ``min(f)`` unless
      ``f`` is guarded, matching the submission's check.
    - ``ORDER BY f ASC`` (ASC is the default) feeding a **row-limited** result
      (``LIMIT`` present): the first row can be a NULL, so "the smallest / earliest"
      is wrong. Only limited results are flagged — a full ordered list is fine.
    """
    guarded = _null_excluded_columns(select)

    for min_node in select.expressions:
        # Peel a projection alias (``MIN(f) AS lo``) to reach the function.
        expr = min_node.this if isinstance(min_node, exp.Alias) else min_node
        if isinstance(expr, exp.Min):
            col = _column_name(expr.this)
            if col and col not in guarded:
                return (
                    f"min({col}) without a NOT NULL guard on {col}: a NULL sorts "
                    "first, so the minimum can be NULL-driven and wrong"
                )

    order = select.args.get("order")
    has_limit = select.args.get("limit") is not None
    if order is not None and has_limit:
        for ordered in order.expressions:
            # Descending is safe (NULLs sort last); ASC is the default when unset.
            if ordered.args.get("desc"):
                continue
            col = _column_name(ordered.this)
            if col and col not in guarded:
                return (
                    f"ORDER BY {col} ASC with LIMIT and no NOT NULL guard on {col}: "
                    "a NULL sorts first, so the top row can be NULL-driven and wrong"
                )
    return None


def _is_minmax_only_projection(select: exp.Select) -> bool:
    """True if ``select`` projects exactly one thing and it is ``MIN(x)``/``MAX(x)``."""
    if len(select.expressions) != 1:
        return False
    only = select.expressions[0]
    only = only.this if isinstance(only, exp.Alias) else only
    return isinstance(only, (exp.Min, exp.Max))


def _check_minmax_subquery(select: exp.Select) -> str | None:
    """Flag ``… = (SELECT MIN/MAX(x) FROM t)`` — the min/max-by-subquery antipattern.

    Selecting the row that owns the extreme value via an equality against a scalar
    ``MIN``/``MAX`` subquery is the shape ``ORDER BY x LIMIT 1`` expresses more
    reliably (and without the two-scan cost). **Diagnostic-grade, tuned for a low
    false-positive rate:** only an *uncorrelated* subquery (no WHERE of its own that
    could reference the outer row) is flagged — a correlated subquery genuinely
    needs the subquery form and is left alone.
    """
    where = select.args.get("where")
    if where is None:
        return None
    for eq in where.find_all(exp.EQ):
        for side in (eq.this, eq.args.get("expression")):
            inner = side.this if isinstance(side, exp.Subquery) else side
            if (
                isinstance(inner, exp.Select)
                and _is_minmax_only_projection(inner)
                and inner.args.get("where") is None  # uncorrelated → safe to flag
            ):
                fn = inner.expressions[0]
                fn = fn.this if isinstance(fn, exp.Alias) else fn
                kind = type(fn).__name__.upper()
                return (
                    f"= (SELECT {kind}(…) …) selects a row by matching a scalar "
                    f"{kind} subquery; ORDER BY … LIMIT 1 is the idiomatic form"
                )
    return None


def _check_field_catenation(select: exp.Select) -> str | None:
    """Flag a projection that string-concatenates two or more **distinct fields**.

    ``a || b`` (or ``CONCAT(a, b)``) of two columns fuses values the question almost
    certainly wants returned separately — a wrong result *shape*. Kept narrow to
    avoid false positives: concatenating a column with a **string literal**
    (formatting, e.g. ``name || ' (' || id`` mixes a literal in) is not flagged
    unless two or more real columns are fused; a single column is never flagged.
    """
    for proj in select.expressions:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        concat_nodes = list(expr.find_all(exp.DPipe, exp.Concat))
        if not concat_nodes:
            continue
        columns = {
            _column_name(c) for node in concat_nodes for c in node.find_all(exp.Column)
        }
        columns.discard(None)
        if len(columns) >= 2:
            joined = ", ".join(sorted(c for c in columns if c))
            return (
                f"projection concatenates distinct fields ({joined}); the question "
                "likely wants them returned as separate columns"
            )
    return None


# A soundness check: inspect one parsed SELECT, return a reason string or ``None``.
SoundnessCheck = Callable[[exp.Select], str | None]

_CHECKS: dict[str, SoundnessCheck] = {
    "null_ordering": _check_null_ordering,
    "minmax_subquery": _check_minmax_subquery,
    "field_catenation": _check_field_catenation,
}

# The checks run, in order, on every SELECT in the candidate; first hit wins. All
# three are correction signals (feed-back), never hard rejects — see module docstring.
DEFAULT_SOUNDNESS_CHECKS: tuple[str, ...] = (
    "null_ordering",
    "minmax_subquery",
    "field_catenation",
)


def check_soundness_sql(
    sql: str | None,
    *,
    dialect: str = DEFAULT_DIALECT,
    checks: Sequence[str] = DEFAULT_SOUNDNESS_CHECKS,
) -> GuardResult:
    """Deterministic bad-construction scan; the pure core the fixture drives.

    Runs each named check on every ``SELECT`` in the candidate and returns the
    first hit as a ``GuardResult`` whose ``REJECT`` means "flagged for correction"
    (not a terminal rejection — the graph feeds it back). ``ALLOW`` when every check
    passes, when there is no SQL, or when the candidate does not parse (parse-safety
    is the guard's job, already run upstream — soundness never fails a run on a
    parse it can't make).
    """
    if not sql or not sql.strip():
        return GuardResult(GuardDecision.ALLOW)

    normalized = _normalize_dialect(dialect)
    tree = _parse(sql, normalized)
    if tree is None:
        return GuardResult(GuardDecision.ALLOW)

    # Soundness judges the **outermost query — the result the user receives** — not
    # every nested SELECT. A scalar ``MIN(x)`` building-block subquery is a common,
    # correct idiom (MIN ignores NULLs); flagging it as a null-ordering hazard would
    # be a false positive. The hazards here (min/asc *result*, min/max-by-subquery
    # *predicate*, catenated *projection*) all live on the top-level select.
    outer = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if outer is None:
        return GuardResult(GuardDecision.ALLOW)
    for name in checks:
        reason = _CHECKS[name](outer)
        if reason is not None:
            return GuardResult(GuardDecision.REJECT, rule=name, reason=reason)
    return GuardResult(GuardDecision.ALLOW)


def _normalize_dialect(dialect: str) -> str | None:
    """Map a prompt dialect name (``"SQLite"``) to a sqlglot key, else ``None``.

    Thin reuse of the same aliases the guard uses; kept local so soundness does not
    import a guard private. Unknown names fall back to the generic parser."""
    aliases = {
        "postgresql": "postgres",
        "postgres": "postgres",
        "sqlite": "sqlite",
        "mysql": "mysql",
        "bigquery": "bigquery",
    }
    return aliases.get(dialect.strip().lower())


def soundness(
    state: RunState,
    *,
    dialect: str = DEFAULT_DIALECT,
    checks: Sequence[str] = DEFAULT_SOUNDNESS_CHECKS,
) -> RunState:
    """Pipeline stage: scan ``state.candidate_sql`` and record a soundness flag.

    On a hit, sets ``state.soundness_flag``/``soundness_reason``/``soundness_rule``
    so the graph can feed the reason back into the next ``generate`` (within the
    capped retry budget) or, if the budget is spent, let the candidate execute
    anyway. On a clean scan the fields are reset so a re-tried candidate is never
    judged by a stale prior flag. Only the decision/rule (never rows) touch the obs
    span. Mutates and returns ``state``.
    """
    with stage_span("soundness", db_id=state.db_id, attempt=state.attempts) as extra:
        result = check_soundness_sql(
            state.candidate_sql, dialect=dialect, checks=checks
        )
        state.soundness_flag = result.rejected
        state.soundness_reason = result.note if result.rejected else None
        state.soundness_rule = result.rule if result.rejected else None
        extra["flagged"] = result.rejected
        if result.rejected:
            extra["rule"] = result.rule
    return state
