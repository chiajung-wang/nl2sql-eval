"""Fixture-driven proof of the result-set comparator (Issues 11, 13).

The golden fixture under ``fixtures/golden_compare/`` — not hand-written asserts
— is the source of truth: this loads every ``(gold, candidate, expected_verdict)``
triple and asserts ``eval.compare.compare`` reproduces its verdict. Adding a case
to the fixture is exercised automatically (CLAUDE.md §8, §10). The unit tests
below pin the contract of individual canonicalization rules (NULL sentinel, float
tolerance, multiset default) beyond what the fixture verdicts alone assert.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from eval.compare import _RULES as RULES
from eval.compare import (
    DEFAULT_RULES,
    FLOAT_DECIMALS,
    NULL_SENTINEL,
    ResultSet,
    Verdict,
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


# --- Issue 13: value- & shape-level canonicalization rules ------------------


def test_default_rules_carry_the_value_shape_canonicalization():
    # The default pipeline is the robust one: position-based columns, NULL
    # normalization, and float tolerance, with `exact` naming the comparison.
    assert DEFAULT_RULES == (
        "column_position",
        "null_sentinel",
        "float_tolerance",
        "exact",
    )


def test_null_sentinel_normalizes_none_to_the_sentinel_value():
    # The rule itself maps every None to the one sentinel, distinct from any
    # real value — proven directly so the contract can't silently drift.
    rule = RULES["null_sentinel"]
    out = rule(ResultSet(columns=("phone",), rows=((None,), ("x",))))
    assert out.rows == ((NULL_SENTINEL,), ("x",))


def test_null_compares_consistently_but_never_equals_a_real_value():
    nulls = {"columns": ["balance"], "rows": [[None]]}
    assert compare(nulls, nulls, "", rules=("null_sentinel", "exact")).correct
    mismatch = compare(
        nulls,
        {"columns": ["balance"], "rows": [[0]]},
        "",
        rules=("null_sentinel", "exact"),
    )
    assert mismatch.verdict is Verdict.INCORRECT


def test_float_tolerance_passes_within_and_fails_outside_the_tolerance():
    within = 0.4 * 10 ** (-FLOAT_DECIMALS)
    outside = 5 * 10 ** (-FLOAT_DECIMALS)
    gold = {"columns": ["avg"], "rows": [[1.0]]}
    near = {"columns": ["avg"], "rows": [[1.0 + within]]}
    far = {"columns": ["avg"], "rows": [[1.0 + outside]]}
    assert compare(gold, near, "", rules=("float_tolerance", "exact")).correct
    assert (
        compare(gold, far, "", rules=("float_tolerance", "exact")).verdict
        is Verdict.INCORRECT
    )


def test_float_tolerance_rounds_decimals_and_leaves_booleans_alone():
    # Decimal (what the SQL driver returns) is rounded like float; bool is an int
    # subclass and must pass through untouched, not be rounded to 0/1.
    rule = RULES["float_tolerance"]
    out = rule(ResultSet(columns=("x", "flag"), rows=((Decimal("1.23456789"), True),)))
    assert out.rows == ((round(Decimal("1.23456789"), FLOAT_DECIMALS), True),)
    assert out.rows[0][1] is True


def test_multiset_is_the_default_count_vs_count_distinct_is_wrong():
    # No de-dup rule exists, so a row-multiplicity difference (COUNT vs COUNT
    # DISTINCT) is a real error under the default pipeline. Set semantics would
    # wrongly pass this.
    result = compare(
        {"columns": ["status"], "rows": [["paid"], ["paid"], ["failed"]]},
        {"columns": ["status"], "rows": [["paid"], ["failed"]]},
        "SELECT status FROM payments;",
    )
    assert result.verdict is Verdict.INCORRECT
