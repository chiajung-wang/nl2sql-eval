"""Canonicalization + result-set comparison (the proven scorer).

Execution accuracy via canonicalized result-set comparison, never SQL
string-match — two different queries can be equally correct (CLAUDE.md §5.1,
§7). Deterministic; no LLM judge, no regex for SQL semantics. Proven against the
golden fixture of ``(gold, candidate, expected_verdict)`` triples under
``fixtures/golden_compare/``. One of the two heavily-tested deterministic cores.

Issue 11 shipped the skeleton: a public ``compare()`` entry point, a
*configurable* canonicalization-rule pipeline that logs which rules ran per
comparison, and the trivial baseline rule — exact value equality of the rows, in
the order returned. The substantive rules slot into the same pipeline in later
Step-2 issues and must never be inlined elsewhere:

- order-insensitivity gated on the gold SQL's ``ORDER BY`` (Issue 12, below),
- column-by-position, NULL sentinel, float tolerance (Issue 13),
- multiset (duplicate) semantics, BIRD-evaluator alignment (Issue 13/14).

A rule is applied to *both* sides before comparison, so a canonicalization can
never make a wrong answer look right — it transforms gold and candidate
identically. Comparison is on result *values*, never the SQL string and (in this
slice) not the column labels either, matching the Step-1 ``gold_matches``
precedent that a correct value under a different alias is still correct.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

logger = logging.getLogger(__name__)

# A result set as produced by the pipeline / stored as gold: ``{"columns": [...],
# "rows": [[...], ...]}``. Only ``rows`` drives the verdict in this slice.
ResultLike = Mapping[str, Any]


class Verdict(StrEnum):
    """The clear, explainable outcome of one comparison."""

    CORRECT = "correct"
    INCORRECT = "incorrect"


@dataclass(frozen=True)
class ResultSet:
    """A canonicalizable result set: column labels + hashable, ordered rows."""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]

    @classmethod
    def from_mapping(cls, result: ResultLike) -> ResultSet:
        columns = tuple(result.get("columns") or [])
        rows = tuple(tuple(row) for row in (result.get("rows") or []))
        return cls(columns=columns, rows=rows)

    @property
    def is_empty(self) -> bool:
        return len(self.rows) == 0


@dataclass(frozen=True)
class RuleContext:
    """Per-comparison context a canonicalization rule may consult.

    Threaded identically into the rule for BOTH sides, so a rule that branches on
    it — e.g. order-insensitivity reading ``gold_sql`` for a top-level
    ``ORDER BY`` — still transforms gold and candidate the same way and can never
    make a wrong answer look right.
    """

    gold_sql: str


# A canonicalization rule rewrites a result set into a canonical form, given the
# per-comparison context. The same rule is applied to BOTH sides before
# comparison, so a rule can never make a wrong answer look right.
CanonRule = Callable[[ResultSet, RuleContext], ResultSet]

_RULES: dict[str, CanonRule] = {}


def register_rule(name: str) -> Callable[[CanonRule], CanonRule]:
    """Register a named canonicalization rule for use in ``compare(rules=...)``.

    Later Step-2 issues register their rules here (order-insensitivity, column
    position, NULL sentinel, float tolerance, multiset, BIRD alignment) without
    touching ``compare()`` itself.
    """

    def _decorate(fn: CanonRule) -> CanonRule:
        _RULES[name] = fn
        return fn

    return _decorate


@register_rule("exact")
def _exact(result: ResultSet, ctx: RuleContext) -> ResultSet:
    """Identity canonicalization: compare rows exactly as returned, in order.

    The trivial baseline (Issue 11). No sorting, no NULL/float/column
    normalization, no multiset relaxation — those are separate, named rules that
    register into this same pipeline in Issues 12-14. Kept available for explicit
    opt-in even though :data:`DEFAULT_RULES` now uses the order-sensitivity rule.
    """
    return result


def _gold_order_is_significant(gold_sql: str) -> bool:
    """True when the gold query's *output* row order is part of correctness.

    A gold query ending in a top-level ``ORDER BY`` declares row order
    significant. An ``ORDER BY`` buried in a subquery, derived table, or CTE body
    does not affect the final row order and is ignored. Detection is sqlglot
    AST-based — never regex or string scanning (CLAUDE.md §4): ``order`` is
    attached only to the outermost SELECT / set-operation node, so an inner
    ``ORDER BY`` lives on the inner node and is correctly skipped.
    """
    try:
        expression = sqlglot.parse_one(gold_sql)
    except ParseError:
        # Gold SQL is validated upstream; an unparseable string here is a harness
        # bug, not a correctness signal. Fall back to order-insensitive (the
        # default) rather than silently asserting that order matters.
        logger.warning("could not parse gold_sql for ORDER BY detection: %r", gold_sql)
        return False
    if expression is None:
        return False
    # Unwrap a parenthesized whole query, e.g. ``(SELECT ... ORDER BY ...)``, so
    # its ORDER BY is still recognized as top-level.
    while isinstance(expression, exp.Subquery):
        expression = expression.this
    return expression.args.get("order") is not None


def _row_sort_key(row: tuple[Any, ...]) -> tuple[tuple[int, str, str], ...]:
    """A total, exception-free ordering key for a row.

    Cells may be heterogeneous or ``None``, which Python cannot order directly;
    this maps each cell to ``(null_rank, type_name, str(value))`` so sorting is
    deterministic and never raises. It exists only to put equal row-multisets
    into the same sequence on both sides — it is *not* value canonicalization
    (NULL/float handling is Issue 13) and never collapses distinct rows.
    """
    return tuple(
        (0, "", "") if cell is None else (1, type(cell).__name__, str(cell))
        for cell in row
    )


@register_rule("order_insensitive")
def _order_insensitive(result: ResultSet, ctx: RuleContext) -> ResultSet:
    """Normalize away row order — UNLESS the gold SQL declares order significant.

    The subtle, false-negative-prone rule (CLAUDE.md domain rule 1): two queries
    returning the same rows in a different order are equally correct, so rows are
    sorted before comparison. The exception is a gold query with a top-level
    ``ORDER BY``: there the order *is* the answer, so rows are left untouched and
    a same-rows/wrong-order candidate is correctly judged incorrect.

    Applied to both sides identically, gated on ``ctx.gold_sql`` (never the
    candidate's), so sorting can never launder a wrong answer.
    """
    if _gold_order_is_significant(ctx.gold_sql):
        return result
    return ResultSet(
        columns=result.columns,
        rows=tuple(sorted(result.rows, key=_row_sort_key)),
    )


# The default rule set. Order-insensitivity gated on the gold's ``ORDER BY``
# (Issue 12) is the baseline correctness rule; the value-level rules (Issue 13+)
# join it here. Kept explicit (not implicit) so every reported verdict names the
# exact canonicalization it was produced under.
DEFAULT_RULES: tuple[str, ...] = ("order_insensitive",)


@dataclass(frozen=True)
class Comparison:
    """A verdict plus the canonicalization that produced it — fully explainable."""

    verdict: Verdict
    applied_rules: tuple[str, ...]
    reason: str

    @property
    def correct(self) -> bool:
        return self.verdict is Verdict.CORRECT


def compare(
    gold_result: ResultLike,
    candidate_result: ResultLike,
    gold_sql: str,
    *,
    rules: Sequence[str] = DEFAULT_RULES,
) -> Comparison:
    """Score ``candidate_result`` against ``gold_result`` by result-set values.

    Canonicalizes both sides through the named ``rules`` (in order), then returns
    a correct/incorrect :class:`Comparison`. ``gold_sql`` is the gold query whose
    answer ``gold_result`` is; it is recorded for explainability and is what the
    order-insensitivity rule (Issue 12) inspects for a top-level ``ORDER BY`` to
    decide whether row order is significant. The empty result set is a distinct,
    correct-able case: two empty result sets compare *correct*, an empty vs a
    non-empty pair compares *incorrect* (empty is never auto-correct).

    Comparison is on values only, never the SQL string (CLAUDE.md §5.1, §7).
    """
    gold = ResultSet.from_mapping(gold_result)
    candidate = ResultSet.from_mapping(candidate_result)

    context = RuleContext(gold_sql=gold_sql)
    applied: list[str] = []
    for name in rules:
        try:
            rule = _RULES[name]
        except KeyError:
            raise ValueError(f"unknown canonicalization rule: {name!r}") from None
        gold = rule(gold, context)
        candidate = rule(candidate, context)
        applied.append(name)

    if gold.rows == candidate.rows:
        verdict = Verdict.CORRECT
        reason = "both result sets empty" if gold.is_empty else "result sets match"
    else:
        verdict = Verdict.INCORRECT
        reason = "result sets differ"

    comparison = Comparison(
        verdict=verdict,
        applied_rules=tuple(applied),
        reason=reason,
    )
    # Log the verdict, the canonicalization that produced it, and the gold SQL —
    # never the result *rows*. The comparator runs upstream of redaction (§5.2),
    # so logging row values here would leak raw PII into traces (§5.3). Rules
    # added in Issues 12-14 must keep this line free of row data.
    logger.info(
        "compare verdict=%s rules=%s reason=%r gold_sql=%r",
        comparison.verdict.value,
        comparison.applied_rules,
        comparison.reason,
        gold_sql,
    )
    return comparison
