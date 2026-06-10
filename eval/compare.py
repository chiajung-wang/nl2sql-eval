"""Canonicalization + result-set comparison (the proven scorer).

Execution accuracy via canonicalized result-set comparison, never SQL
string-match — two different queries can be equally correct (CLAUDE.md §5.1,
§7). Deterministic; no LLM judge, no regex for SQL semantics. Proven against the
golden fixture of ``(gold, candidate, expected_verdict)`` triples under
``fixtures/golden_compare/``. One of the two heavily-tested deterministic cores.

Issue 11 (this slice) ships the skeleton only: a public ``compare()`` entry
point, a *configurable* canonicalization-rule pipeline that logs which rules ran
per comparison, and the trivial baseline rule — exact value equality of the
rows, in the order returned. The substantive rules slot into the same pipeline
in later Step-2 issues and must never be inlined here:

- order-insensitivity gated on the gold SQL's ``ORDER BY`` (Issue 12),
- column-by-position, NULL sentinel, float tolerance (Issue 12/13),
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


# The default rule set. Trivial-only for now; grows as the substantive rules
# land. Kept explicit (not implicit) so every reported verdict names the exact
# canonicalization it was produced under.
DEFAULT_RULES: tuple[str, ...] = ("exact",)


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
