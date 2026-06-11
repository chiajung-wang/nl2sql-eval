"""Fixture-driven proof of the result-set comparator (Issues 11, 12, 13).

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
    BIRD_RULES,
    DEFAULT_RULES,
    FLOAT_DECIMALS,
    NULL_SENTINEL,
    ResultSet,
    RuleContext,
    Verdict,
    _gold_order_is_significant,
    compare,
)

# A throwaway context for exercising a single value/shape rule in isolation —
# those rules ignore it, but the CanonRule signature requires it.
_NO_CTX = RuleContext(gold_sql="")

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


def test_default_rules_are_the_full_canonicalization_pipeline():
    # The default pipeline is the robust one: position-based columns, NULL
    # normalization, and float tolerance (Issue 13) run BEFORE order-insensitivity
    # (Issue 12), with `exact` naming the final value-equality comparison. The
    # value rules must precede the order rule so sorting sees already-normalized
    # cells (see DEFAULT_RULES rationale in eval/compare.py).
    assert DEFAULT_RULES == (
        "column_position",
        "null_sentinel",
        "float_tolerance",
        "order_insensitive",
        "exact",
    )


# --- Issue 13: value- & shape-level canonicalization rules ------------------


def test_null_sentinel_normalizes_none_to_the_sentinel_value():
    # The rule itself maps every None to the one sentinel, distinct from any
    # real value — proven directly so the contract can't silently drift.
    rule = RULES["null_sentinel"]
    out = rule(ResultSet(columns=("phone",), rows=((None,), ("x",))), _NO_CTX)
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
    out = rule(
        ResultSet(columns=("x", "flag"), rows=((Decimal("1.23456789"), True),)),
        _NO_CTX,
    )
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


# --- Issue 14: BIRD-evaluator alignment -------------------------------------


def test_set_rule_dedups_and_is_order_insensitive():
    # The 'set' rule is the BIRD primitive: it collapses duplicates AND sorts to
    # a canonical order, regardless of the gold's ORDER BY (it never reads it).
    rule = RULES["set"]
    out = rule(
        ResultSet(columns=("s",), rows=(("paid",), ("failed",), ("paid",))),
        RuleContext(gold_sql="SELECT s FROM t ORDER BY s"),
    )
    assert out.rows == (("failed",), ("paid",))


def test_bird_rules_reproduce_set_comparison_semantics():
    # BIRD_RULES == set(predicted) == set(ground_truth): order- and
    # duplicate-insensitive. A reordered, de-duplicated candidate passes.
    result = compare(
        {"columns": ["s"], "rows": [["a"], ["a"], ["b"]]},
        {"columns": ["s"], "rows": [["b"], ["a"]]},
        "SELECT s FROM t ORDER BY s",
        rules=BIRD_RULES,
    )
    assert result.correct
    assert result.applied_rules == BIRD_RULES


def test_default_and_bird_rules_diverge_on_the_same_data():
    # The whole point of Issue 14: on data where row order matters (gold ORDER
    # BY) and duplicates differ, BIRD's set() passes what our default rejects.
    # The gap between the two verdicts is exactly what BIRD's evaluator masks.
    gold = {"columns": ["s"], "rows": [["a"], ["a"], ["b"]]}
    candidate = {"columns": ["s"], "rows": [["b"], ["a"]]}
    gold_sql = "SELECT s FROM t ORDER BY s"
    assert compare(gold, candidate, gold_sql, rules=BIRD_RULES).correct
    assert compare(gold, candidate, gold_sql).verdict is Verdict.INCORRECT


def test_bird_rules_have_no_float_tolerance():
    # BIRD compares floats exactly; BIRD_RULES omits float_tolerance, so 9th-
    # decimal noise that our default forgives is judged wrong under BIRD.
    gold = {"columns": ["avg"], "rows": [[42.66666667]]}
    near = {"columns": ["avg"], "rows": [[42.666666673]]}
    assert "float_tolerance" not in BIRD_RULES
    assert compare(gold, near, "", rules=BIRD_RULES).verdict is Verdict.INCORRECT
    assert compare(gold, near, "").correct  # default forgives it
