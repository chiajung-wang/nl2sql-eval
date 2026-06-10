"""Fixture-driven proof of the result-set comparator (Issue 11).

The golden fixture under ``fixtures/golden_compare/`` — not hand-written asserts
— is the source of truth: this loads every ``(gold, candidate, expected_verdict)``
triple and asserts ``eval.compare.compare`` reproduces its verdict. Adding a case
to the fixture is exercised automatically (CLAUDE.md §8, §10).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.compare import DEFAULT_RULES, Verdict, compare

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden_compare"


def _load_cases() -> list:
    cases = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        for case in data["cases"]:
            cases.append(pytest.param(case, id=f"{path.stem}:{case['id']}"))
    return cases


GOLDEN_CASES = _load_cases()


def test_fixture_is_non_empty():
    # Guards against a glob/parse regression silently turning the proof into a
    # no-op (zero parametrized cases would otherwise "pass").
    assert GOLDEN_CASES, "no golden_compare cases loaded — fixture missing/unparseable"


@pytest.mark.parametrize("case", GOLDEN_CASES)
def test_golden_compare(case):
    rules = tuple(case["rules"]) if "rules" in case else DEFAULT_RULES
    result = compare(
        case["gold_result"],
        case["candidate_result"],
        case.get("gold_sql", ""),
        rules=rules,
    )
    assert result.verdict.value == case["expected_verdict"], (
        f"{case['id']}: {result.reason} (rules={result.applied_rules})"
    )


# --- the comparator's contract beyond the fixture verdicts ------------------


def test_applied_rules_are_logged_on_the_comparison():
    one_row = {"columns": ["n"], "rows": [[1]]}
    result = compare(one_row, one_row, "")
    assert result.applied_rules == DEFAULT_RULES
    assert result.correct is True


def test_unknown_rule_is_rejected():
    with pytest.raises(ValueError, match="unknown canonicalization rule"):
        compare({"rows": []}, {"rows": []}, "", rules=("not-a-rule",))


def test_verdict_is_value_based_not_column_name_based():
    # Same value, different column label → still correct (CLAUDE.md domain rule 1).
    result = compare(
        {"columns": ["n"], "rows": [[3]]},
        {"columns": ["us_user_count"], "rows": [[3]]},
        "SELECT count(*) AS n FROM users WHERE country = 'US';",
    )
    assert result.verdict is Verdict.CORRECT
