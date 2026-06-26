"""The diagnostic's deterministic core — AST-based failure tagging, offline.

The live run is the AFK part; the tagging logic (sqlglot feature diff of gold vs
candidate) is pure and pinned here: each structural difference yields its tag, a
matching shape yields the value-level sentinel, and unparseable candidates are
flagged rather than crashing.
"""

from __future__ import annotations

from eval.diagnose_bird import categorize


def test_missing_join_and_table_mismatch():
    gold = "SELECT u.name FROM users u JOIN orders o ON o.uid = u.id WHERE o.paid = 1"
    cand = "SELECT name FROM users WHERE paid = 1"
    tags = categorize(gold, cand)
    assert "join_mismatch" in tags
    assert "table_mismatch" in tags


def test_aggregate_mismatch():
    tags = categorize(
        "SELECT SUM(amount) FROM payments", "SELECT COUNT(amount) FROM payments"
    )
    assert "aggregate_mismatch" in tags


def test_group_by_mismatch():
    tags = categorize(
        "SELECT cat, COUNT(*) FROM t GROUP BY cat", "SELECT cat, COUNT(*) FROM t"
    )
    assert "group_by_mismatch" in tags


def test_top_n_limit_mismatch():
    tags = categorize(
        "SELECT name FROM t ORDER BY score DESC LIMIT 1", "SELECT name FROM t"
    )
    assert "limit_mismatch" in tags


def test_projection_count_mismatch():
    tags = categorize("SELECT a, b FROM t", "SELECT a FROM t")
    assert "projection_count_mismatch" in tags


def test_matching_shape_is_value_level():
    # Same structure, different (value-level) predicate — no structural tag fires;
    # the failure is finer than shape, which is itself the signal.
    gold = "SELECT name FROM users WHERE country = 'US'"
    cand = "SELECT name FROM users WHERE country = 'USA'"
    assert categorize(gold, cand) == ["shape_matches_value_level"]


def test_unparseable_candidate_is_flagged_not_crashed():
    assert categorize("SELECT 1 FROM t", "this is not sql ))(") == [
        "candidate_unparseable"
    ]
    assert categorize("SELECT 1 FROM t", None) == ["candidate_unparseable"]
