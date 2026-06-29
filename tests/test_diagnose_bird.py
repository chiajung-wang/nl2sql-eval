"""The diagnostic's deterministic core — AST-based failure tagging, offline.

The live run is the AFK part; the tagging logic (sqlglot feature diff of gold vs
candidate) is pure and pinned here: each structural difference yields its tag, a
matching shape yields the value-level sentinel, and unparseable candidates are
flagged rather than crashing.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from eval.datasets.bird import loader
from eval.diagnose_bird import categorize, rescore_under_bird

# A query that never terminates without a bound — an infinite recursive CTE.
# Stands in for the runaway candidates a truncated/garbled model can emit (#125).
_RUNAWAY = (
    "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) "
    "SELECT count(*) FROM r"
)


def _memory_engine_with_table():
    # StaticPool so the in-memory db (and its table) survive across connections.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.execute(text("INSERT INTO t VALUES (1), (2), (3)"))
    return engine


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


# --- #125: a runaway candidate must not hang the diagnostic --------------------


def test_run_query_timeout_aborts_a_runaway_query():
    # The progress-handler bound aborts an otherwise-infinite query quickly
    # (raising) rather than hanging — and well within a generous test ceiling.
    engine = _memory_engine_with_table()
    start = time.monotonic()
    with pytest.raises(Exception):  # noqa: B017 — sqlite3/SQLAlchemy OperationalError
        loader.run_query(engine, _RUNAWAY, timeout=0.5)
    assert time.monotonic() - start < 5.0


def test_run_query_without_timeout_is_unchanged():
    # Default (no timeout) keeps the original behavior for the harness's gold path.
    engine = _memory_engine_with_table()
    assert loader.run_query(engine, "SELECT count(*) AS n FROM t") == {
        "columns": ["n"],
        "rows": [(3,)],
    }
    # ...and a timeout set on a fast query returns the same correct result.
    assert loader.run_query(engine, "SELECT count(*) AS n FROM t", timeout=5)[
        "rows"
    ] == [(3,)]


def test_rescore_completes_and_marks_runaway_candidate_failed(monkeypatch):
    # rescore_under_bird re-executes untrusted candidate SQL; a runaway one must
    # be bounded (timed out -> caught) so the loop finishes instead of hanging,
    # and the record is left as a genuine failure (bird_correct False).
    engine = _memory_engine_with_table()
    monkeypatch.setattr("eval.diagnose_bird._engine", lambda _db_id: engine)
    monkeypatch.setattr("eval.diagnose_bird._RESCORE_TIMEOUT_S", 0.5)
    records = [
        {"db_id": "x", "gold_sql": "SELECT x FROM t", "candidate_sql": _RUNAWAY},
        {"db_id": "x", "gold_sql": "SELECT x FROM t", "candidate_sql": None},
    ]
    start = time.monotonic()
    rescore_under_bird(records)
    assert time.monotonic() - start < 5.0  # finished, didn't hang
    assert records[0]["bird_correct"] is False
    assert records[1]["bird_correct"] is False
