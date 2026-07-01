"""Literal→field matching / steering (Step 12, #141) — offline unit coverage.

The deterministic core of the paper's literal-matching loop (arXiv:2505.19988v2 §3)
is fully offline and proven here: the sampled value index, the sqlglot-AST literal
extraction + on-column check, the steering message, and the graph wiring that feeds
an off-column literal back to ``generate`` (with an injected fake generator — no
network, no key). The live A/B and its trigger/recovery/false-steer rates are
deferred (gated on a key).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from nl2sql.pipeline.correct import correct_literal
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.literal_check import (
    check_literals,
    literal_check,
    steering_message,
)
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import build_schema_index
from nl2sql.value_index import build_value_index, normalize_value
from tests.test_pipeline_loop import FakeLLMClient

# A district name that lives in the District column; constraining it against
# CountyName is the off-column error the steering fixes. Shared to keep SQL short.
DISTRICT = "Fresno County Office of Education"
OFF = f"SELECT id FROM schools WHERE CountyName = '{DISTRICT}'"
ON = f"SELECT id FROM schools WHERE District = '{DISTRICT}'"


@pytest.fixture
def schools_engine():
    """A db where the same class of literal (a district name) lives in one column
    (District), so a constraint against CountyName is the off-column error."""
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE schools (id INTEGER, CountyName TEXT, District TEXT)")
        )
        conn.execute(
            text(
                "INSERT INTO schools VALUES "
                "(1,'Fresno','Fresno County Office of Education'), "
                "(2,'Kern','Bakersfield City Elementary')"
            )
        )
    return engine


# --- value index ------------------------------------------------------------


def test_value_index_maps_value_to_its_column(schools_engine):
    idx = build_value_index(schools_engine)
    assert idx.columns_containing("Fresno County Office of Education") == frozenset(
        {"schools.district"}
    )
    assert idx.column_contains("schools.district", "Fresno County Office of Education")
    assert not idx.column_contains("schools.countyname", DISTRICT)


def test_value_index_is_case_and_whitespace_insensitive(schools_engine):
    idx = build_value_index(schools_engine)
    assert idx.columns_containing("  fresno  ") == frozenset({"schools.countyname"})


def test_value_index_tracks_which_columns_were_sampled(schools_engine):
    idx = build_value_index(schools_engine)
    assert idx.is_indexed("schools.district")
    assert not idx.is_indexed("schools.nonexistent")


def test_value_index_skips_redacted_columns(schools_engine):
    idx = build_value_index(
        schools_engine, redact_columns=frozenset({"schools.district"})
    )
    # A PII column is never indexed — its values can't surface in a steering prompt.
    assert not idx.is_indexed("schools.district")
    assert idx.columns_containing("Fresno County Office of Education") == frozenset()


def test_normalize_value():
    assert normalize_value("  Fresno ") == "fresno"
    assert normalize_value(42) == "42"


# --- literal check (sqlglot-AST extraction + lookup) ------------------------


def test_off_column_literal_is_flagged(schools_engine):
    idx = build_value_index(schools_engine)
    sql = OFF
    findings = check_literals(sql, idx, dialect="SQLite")
    assert len(findings) == 1
    assert findings[0].constrained_column == "CountyName"
    assert findings[0].candidate_columns == ("schools.district",)


def test_on_column_literal_is_not_flagged(schools_engine):
    idx = build_value_index(schools_engine)
    sql = ON
    assert check_literals(sql, idx, dialect="SQLite") == []


def test_alias_qualified_column_resolves(schools_engine):
    idx = build_value_index(schools_engine)
    sql = (
        "SELECT s.id FROM schools s "
        "WHERE s.CountyName = 'Fresno County Office of Education'"
    )
    findings = check_literals(sql, idx, dialect="SQLite")
    assert findings and findings[0].candidate_columns == ("schools.district",)


def test_unknown_literal_does_not_steer(schools_engine):
    # A value that occurs in no sampled column can't be helped — never steer.
    idx = build_value_index(schools_engine)
    sql = "SELECT id FROM schools WHERE CountyName = 'Nowhere At All'"
    assert check_literals(sql, idx, dialect="SQLite") == []


def test_in_clause_literals_are_checked(schools_engine):
    idx = build_value_index(schools_engine)
    sql = (
        "SELECT id FROM schools "
        "WHERE CountyName IN ('Fresno County Office of Education', 'Kern')"
    )
    findings = check_literals(sql, idx, dialect="SQLite")
    # Only the district-name literal is off-column; 'Kern' is a real CountyName value.
    assert len(findings) == 1
    assert findings[0].literal == "Fresno County Office of Education"


def test_unparseable_sql_returns_no_findings(schools_engine):
    idx = build_value_index(schools_engine)
    assert check_literals("not sql at all", idx, dialect="SQLite") == []
    assert check_literals("", idx, dialect="SQLite") == []


def test_numeric_and_non_string_literals_are_ignored(schools_engine):
    # The check is about string literals bound to a column; a numeric id constraint
    # is out of scope (never a "wrong column for this value" case here).
    idx = build_value_index(schools_engine)
    sql = "SELECT id FROM schools WHERE id = 1"
    assert check_literals(sql, idx, dialect="SQLite") == []


def test_steering_message_names_the_columns(schools_engine):
    idx = build_value_index(schools_engine)
    sql = OFF
    msg = steering_message(check_literals(sql, idx, dialect="SQLite"))
    assert "does not occur in CountyName" in msg
    assert "schools.district" in msg


# --- stage + correct_literal ------------------------------------------------


def test_literal_check_stage_records_flag(schools_engine):
    idx = build_value_index(schools_engine)
    state = RunState(question="q", db_id="schools")
    state.candidate_sql = OFF
    literal_check(state, idx, dialect="SQLite")
    assert state.literal_flag and state.literal_reason


def test_literal_check_no_index_is_noop():
    state = RunState(question="q", db_id="schools")
    state.candidate_sql = "SELECT id FROM schools WHERE CountyName = 'x'"
    literal_check(state, None, dialect="SQLite")
    assert state.literal_flag is False


def test_correct_literal_stages_feedback_then_clears():
    state = RunState(question="q", db_id="schools")
    state.candidate_sql = "SELECT 1"
    state.literal_flag = True
    state.literal_reason = "The value 'x' does not occur in A; it occurs in b.c."
    correct_literal(state)
    assert state.correction["error"].startswith("The value 'x'")
    assert state.literal_flag is False


def test_correct_literal_noop_when_unflagged():
    state = RunState(question="q", db_id="schools")
    correct_literal(state)
    assert state.correction is None


# --- graph wiring -----------------------------------------------------------


def test_off_column_literal_feeds_back_and_regenerates(schools_engine):
    index = build_schema_index(schools_engine)
    vindex = build_value_index(schools_engine)
    client = FakeLLMClient(
        [
            OFF,
            ON,
        ]
    )
    state = run_pipeline(
        "which school",
        schema_index=index,
        engine=schools_engine,
        db_id="schools",
        dialect="SQLite",
        client=client,
        value_index=vindex,
        max_attempts=3,
    )
    assert len(client.calls) == 2  # steered once, then the corrected candidate ran
    assert state.literal_flag is False
    assert state.result_rows == [(1,)]


def test_no_value_index_skips_the_check(schools_engine):
    index = build_schema_index(schools_engine)
    client = FakeLLMClient([OFF])
    state = run_pipeline(
        "which school",
        schema_index=index,
        engine=schools_engine,
        db_id="schools",
        dialect="SQLite",
        client=client,
        max_attempts=3,
    )
    assert len(client.calls) == 1  # no index → literal_check is a no-op
    assert state.literal_flag is False


def test_off_column_literal_executes_when_budget_spent(schools_engine):
    index = build_schema_index(schools_engine)
    vindex = build_value_index(schools_engine)
    # Always off-column; with the budget spent it must still execute (never lost).
    client = FakeLLMClient([OFF])
    state = run_pipeline(
        "which school",
        schema_index=index,
        engine=schools_engine,
        db_id="schools",
        dialect="SQLite",
        client=client,
        value_index=vindex,
        max_attempts=2,
    )
    assert state.result_rows == []  # ran (CountyName has no such value), not dropped
    assert len(client.calls) == 2  # one steer retry, then budget spent → execute
