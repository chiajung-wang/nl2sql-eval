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

from eval.compare import (
    DEFAULT_RULES,
    Verdict,
    _gold_order_is_significant,
    compare,
)

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


# --- the ORDER BY conditional (Issue 12) ------------------------------------


@pytest.mark.parametrize(
    ("gold_sql", "significant"),
    [
        ("SELECT name FROM merchants ORDER BY name", True),
        ("SELECT name FROM merchants ORDER BY signup_date DESC", True),
        ("SELECT name FROM merchants", False),
        ("SELECT name FROM merchants WHERE category = 'software'", False),
        # ORDER BY confined to a subquery / derived table / CTE body does not
        # affect the final row order → not significant.
        ("SELECT a FROM t WHERE x IN (SELECT b FROM u ORDER BY b)", False),
        ("SELECT a FROM (SELECT a FROM t ORDER BY a) sub", False),
        ("WITH c AS (SELECT a FROM t ORDER BY a) SELECT a FROM c", False),
        # Top-level ORDER BY on a set operation / after a CTE → significant.
        ("SELECT a FROM t UNION SELECT a FROM u ORDER BY a", True),
        ("WITH c AS (SELECT a FROM t) SELECT a FROM c ORDER BY a", True),
        # A parenthesized whole query keeps its ORDER BY top-level.
        ("(SELECT a FROM t ORDER BY a)", True),
        # Unparseable / empty gold falls back to order-insensitive.
        ("", False),
    ],
)
def test_order_significance_detection_is_ast_based(gold_sql, significant):
    assert _gold_order_is_significant(gold_sql) is significant


def test_order_detection_ignores_order_by_inside_a_string_literal():
    # A regex/string scan would false-positive on "ORDER BY" appearing in a
    # value; AST parsing does not (CLAUDE.md §4).
    gold_sql = "SELECT label FROM t WHERE label = 'ORDER BY x'"
    assert _gold_order_is_significant(gold_sql) is False


def test_order_rule_is_the_default():
    assert DEFAULT_RULES == ("order_insensitive",)
