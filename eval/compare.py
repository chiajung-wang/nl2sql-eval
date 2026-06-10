"""Canonicalization + result-set comparison (the proven scorer).

Execution accuracy via canonicalized result-set comparison, never SQL
string-match — two different queries can be equally correct (CLAUDE.md §5.1,
§7). Deterministic; no LLM judge, no regex for SQL semantics. Proven against the
golden fixture of ``(gold, candidate, expected_verdict)`` triples under
``fixtures/golden_compare/``. One of the two heavily-tested deterministic cores.

Issue 11 shipped the skeleton: a public ``compare()`` entry point, a
*configurable* canonicalization-rule pipeline that logs which rules ran per
comparison, and the trivial baseline rule — exact value equality of the rows, in
the order returned. The substantive rules slot into the same pipeline and must
never be inlined into ``compare()``:

- order-insensitivity gated on the gold SQL's ``ORDER BY`` (Issue 12),
- column-by-position, NULL sentinel, float tolerance (Issue 13 — this slice),
- multiset (duplicate) semantics by default (Issue 13 — by omission of a de-dup
  rule), BIRD-evaluator alignment (Issue 14).

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
from decimal import Decimal
from enum import StrEnum
from typing import Any

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


# A canonicalization rule rewrites a result set into a canonical form. The same
# rule is applied to BOTH sides before comparison, so a rule can never make a
# wrong answer look right.
CanonRule = Callable[[ResultSet], ResultSet]

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
def _exact(result: ResultSet) -> ResultSet:
    """Identity canonicalization: compare rows exactly as returned, in order.

    The trivial baseline (Issue 11). No sorting, no NULL/float/column
    normalization, no multiset relaxation — those are separate, named rules that
    register into this same pipeline in Issues 12-14.
    """
    return result


# --- Issue 13: value- & shape-level canonicalization ------------------------
#
# Each rule is a transform applied to BOTH sides (see :data:`CanonRule`), so it
# can only let equally-correct queries compare equal — it can never make a wrong
# answer look right. None of these touches row *order*: ordering is gated on the
# gold SQL's ``ORDER BY`` and lives in its own rule (Issue 12); re-implementing
# it here would double-sort. **Multiset (duplicate) semantics are the default by
# omission** — there is deliberately no de-dup rule, so two results that differ
# only in row multiplicity (the classic ``COUNT`` vs ``COUNT DISTINCT`` bug)
# stay distinct and compare *incorrect*. A future ``set`` rule would be the
# canonicalization; its absence is what makes the comparator multiset.

# The single normal form every SQL NULL collapses to, so NULLs compare
# consistently regardless of how a driver spells them and so they are hashable /
# orderable for later rules. Distinct from any real value (e.g. the string
# "None" or 0), so NULL never silently equals a non-NULL.
NULL_SENTINEL = "\x00__NULL__\x00"

# Floats are rounded to this many decimal places before comparison, so
# insignificant precision noise (e.g. an ``AVG`` differing in the 9th digit)
# does not register as a wrong answer, while a genuinely different number still
# does. A fixed, logged constant — not a per-call knob — keeps every verdict
# reproducible.
FLOAT_DECIMALS = 6


def _map_cells(result: ResultSet, fn: Callable[[Any], Any]) -> ResultSet:
    """Apply ``fn`` to every cell, preserving row/column shape and order."""
    rows = tuple(tuple(fn(cell) for cell in row) for row in result.rows)
    return ResultSet(columns=result.columns, rows=rows)


@register_rule("column_position")
def _column_position(result: ResultSet) -> ResultSet:
    """Match columns by position, not by name (CLAUDE.md domain rule 1).

    Replaces the column *labels* with positional placeholders so an alias,
    rename, or relabel of an otherwise-correct query cannot fail it. The verdict
    is computed from row *values* in positional order; a genuine column-order
    error (values transposed between positions) still differs and is caught.
    This rule makes the value-only, position-based matching explicit and logged
    — it is the seam where a stricter label-aware rule could later be swapped in.
    """
    columns = tuple(f"col_{i}" for i in range(len(result.columns)))
    return ResultSet(columns=columns, rows=result.rows)


@register_rule("null_sentinel")
def _null_sentinel(result: ResultSet) -> ResultSet:
    """Normalize every SQL NULL (``None``) to a single sentinel.

    NULLs then compare consistently across both sides and become hashable /
    orderable for downstream rules. The sentinel is distinct from any real value,
    so a NULL never collapses into ``0``, ``""``, or the string ``"None"``.
    """
    return _map_cells(result, lambda c: NULL_SENTINEL if c is None else c)


@register_rule("float_tolerance")
def _float_tolerance(result: ResultSet) -> ResultSet:
    """Round floats/decimals to :data:`FLOAT_DECIMALS` places before comparing.

    Within-tolerance precision differences then compare equal; an
    out-of-tolerance difference still differs and is judged wrong. ``bool`` is an
    ``int`` subclass but is left untouched; non-numeric cells pass through.
    """

    def _round(cell: Any) -> Any:
        if isinstance(cell, bool):
            return cell
        if isinstance(cell, (float, Decimal)):
            return round(cell, FLOAT_DECIMALS)
        return cell

    return _map_cells(result, _round)


# The default rule set. Position-based column matching, NULL normalization, and
# float tolerance are always-on for a trustworthy scorer; ``exact`` names the
# final value-equality comparison. Order-insensitivity (Issue 12) and BIRD
# reconciliation (Issue 14) extend this tuple. Kept explicit (not implicit) so
# every reported verdict names the exact canonicalization it was produced under.
DEFAULT_RULES: tuple[str, ...] = (
    "column_position",
    "null_sentinel",
    "float_tolerance",
    "exact",
)


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
    order-insensitivity rule (Issue 12) will inspect for ``ORDER BY`` — this
    slice does not branch on it. The empty result set is a distinct,
    correct-able case: two empty result sets compare *correct*, an empty vs a
    non-empty pair compares *incorrect* (empty is never auto-correct).

    Comparison is on values only, never the SQL string (CLAUDE.md §5.1, §7).
    """
    gold = ResultSet.from_mapping(gold_result)
    candidate = ResultSet.from_mapping(candidate_result)

    applied: list[str] = []
    for name in rules:
        try:
            rule = _RULES[name]
        except KeyError:
            raise ValueError(f"unknown canonicalization rule: {name!r}") from None
        gold = rule(gold)
        candidate = rule(candidate)
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
