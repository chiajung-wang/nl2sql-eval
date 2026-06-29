"""Loop-aware re-trigger (Step 6, issue #46) — not-found error → re-retrieve.

A ``column/table-not-found`` execution error routes back into retrieval and
widens the schema the generator sees, inside the Step-5 capped budget. Offline:
an in-memory SQLite db + the injected FakeLLMClient, so we can assert the *second*
attempt's prompt carried more of the schema than the first.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.retrieve import is_not_found_error, missing_identifier
from nl2sql.schema_index import build_schema_index
from tests.test_pipeline_loop import FakeLLMClient


@pytest.fixture
def abc_engine():
    """Three tables; only ``alpha`` matches the test question lexically."""
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alpha (id INTEGER PRIMARY KEY, n INTEGER)"))
        conn.execute(text("CREATE TABLE beta (id INTEGER PRIMARY KEY, n INTEGER)"))
        conn.execute(text("CREATE TABLE gamma (id INTEGER PRIMARY KEY, n INTEGER)"))
        conn.execute(text("INSERT INTO alpha (n) VALUES (1), (2)"))
    return engine


def _n_tables(prompt: str) -> int:
    return prompt.count("CREATE TABLE ")


# --- the not-found classifier -----------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        "(sqlite3.OperationalError) no such table: ghost",
        "(sqlite3.OperationalError) no such column: foo",
        'relation "ghost" does not exist',
        'column "foo" does not exist',
    ],
)
def test_is_not_found_error_true_for_missing_table_or_column(error):
    assert is_not_found_error(error) is True


@pytest.mark.parametrize(
    "error",
    [
        None,
        "",
        '(sqlite3.OperationalError) near "FROM": syntax error',
        "division by zero",
    ],
)
def test_is_not_found_error_false_otherwise(error):
    assert is_not_found_error(error) is False


@pytest.mark.parametrize(
    "error, expected",
    [
        ("(sqlite3.OperationalError) no such table: ghost", "ghost"),
        ("(sqlite3.OperationalError) no such column: foo", "foo"),
        ('relation "ghost" does not exist', "ghost"),
        ('column "foo" does not exist', "foo"),
        # The hint is the bare name — never the message's stopwords.
        ("no such table: ghost", "ghost"),
        ('near "FROM": syntax error', ""),
        (None, ""),
    ],
)
def test_missing_identifier_extracts_the_bare_name(error, expected):
    assert missing_identifier(error) == expected


# --- the re-trigger in the pipeline -----------------------------------------


def test_not_found_error_re_retrieves_a_wider_schema_and_recovers(abc_engine):
    index = build_schema_index(abc_engine)
    # Attempt 1 reaches for a table that doesn't exist → not-found. Attempt 2 (a
    # wider retrieval) writes valid SQL against a real, retrieved table.
    client = FakeLLMClient(
        reply=[
            "SELECT count(*) AS n FROM ghost",
            "SELECT count(*) AS n FROM alpha",
        ]
    )

    state = run_pipeline(
        "count alpha rows",
        schema_index=index,
        budget_tokens=None,  # always-RAG: exercise the re-retrieve widening
        engine=abc_engine,
        db_id="abc",
        dialect="SQLite",
        client=client,
        max_attempts=2,
        max_tables=1,
    )

    assert state.error is None
    assert state.attempts == 2
    # The re-retrieve widened the schema: attempt 2's prompt has more tables.
    first, second = (
        client.calls[0]["messages"][0]["content"],
        client.calls[1]["messages"][0]["content"],
    )
    assert _n_tables(first) == 1
    assert _n_tables(second) > _n_tables(first)
    # And the widened set is recorded on the state (recall metric reads this).
    assert state.retrieved_tables is not None
    assert len(state.retrieved_tables) >= 2


def test_column_not_found_on_in_scope_table_re_retrieves_via_execution(abc_engine):
    # Distinct from the table cases: an IN-SCOPE table with a missing column passes
    # table-scope and actually executes, producing a genuine "no such column"
    # execution error — exercising the not-found *execution* re-retrieve branch
    # (#46), which the table-scope guard (#48) now intercepts for tables.
    index = build_schema_index(abc_engine)
    client = FakeLLMClient(
        reply=[
            "SELECT bad_col AS n FROM alpha",  # in scope → executes → no such column
            "SELECT count(*) AS n FROM alpha",
        ]
    )

    state = run_pipeline(
        "count alpha rows",
        schema_index=index,
        budget_tokens=None,  # always-RAG: exercise the re-retrieve widening
        engine=abc_engine,
        db_id="abc",
        dialect="SQLite",
        client=client,
        max_attempts=2,
        max_tables=1,
    )

    assert state.error is None  # recovered on attempt 2
    assert state.attempts == 2
    assert not state.guard_rejected  # the failure was an execution error, not the gate
    first, second = (
        client.calls[0]["messages"][0]["content"],
        client.calls[1]["messages"][0]["content"],
    )
    assert _n_tables(second) > _n_tables(first)  # the not-found error widened retrieval


def test_non_not_found_error_regenerates_without_re_retrieving(abc_engine):
    index = build_schema_index(abc_engine)
    # An unknown-function error parses fine (so it clears the guard) but is not a
    # retrieval problem: regenerate, don't widen the schema.
    client = FakeLLMClient(
        reply=[
            "SELECT no_such_func(n) AS n FROM alpha",  # → "no such function: …"
            "SELECT count(*) AS n FROM alpha",
        ]
    )

    state = run_pipeline(
        "count alpha rows",
        schema_index=index,
        budget_tokens=None,  # always-RAG: exercise the re-retrieve widening
        engine=abc_engine,
        db_id="abc",
        dialect="SQLite",
        client=client,
        max_attempts=2,
        max_tables=1,
    )

    assert state.error is None
    assert state.attempts == 2
    # Schema stayed narrow across both attempts — no re-retrieve fired.
    first, second = (
        client.calls[0]["messages"][0]["content"],
        client.calls[1]["messages"][0]["content"],
    )
    assert _n_tables(first) == 1 and _n_tables(second) == 1
    assert state.retrieved_tables == ["alpha"]


def test_re_retrieve_stays_inside_the_budget(abc_engine):
    index = build_schema_index(abc_engine)
    # Every attempt reaches for a table outside the db: the loop re-triggers
    # retrieval (widening) yet still stops at the budget — no infinite re-retrieval.
    # With table-scope wired in (Step 6, #48), the out-of-scope table is caught
    # *pre-execution*, so budget exhaustion ends the run as a terminal
    # GUARDRAIL_REJECTED — never executed — rather than a not-found retry-exhaust.
    client = FakeLLMClient(reply="SELECT count(*) AS n FROM ghost")

    state = run_pipeline(
        "count alpha rows",
        schema_index=index,
        budget_tokens=None,  # always-RAG: exercise the re-retrieve widening
        engine=abc_engine,
        db_id="abc",
        dialect="SQLite",
        client=client,
        max_attempts=3,
        max_tables=1,
    )

    assert state.guard_rejected is True
    assert state.guard_rule == "table_scope"
    assert state.error is None  # the gate stopped it; it never executed
    assert state.attempts == 3
    assert len(client.calls) == 3
    # Widening eventually reached the full schema (3 tables).
    assert state.retrieved_tables == ["alpha", "beta", "gamma"]


def test_baseline_path_does_not_re_retrieve(abc_engine):
    # No index → the not-found error can only drive regeneration (no retrieval to
    # re-trigger). Confirms the re-trigger is gated on schema-RAG being in use.
    client = FakeLLMClient(
        reply=[
            "SELECT count(*) AS n FROM ghost",
            "SELECT count(*) AS n FROM alpha",
        ]
    )

    state = run_pipeline(
        "count alpha rows",
        schema="CREATE TABLE alpha (id INT, n INT);",
        engine=abc_engine,
        db_id="abc",
        dialect="SQLite",
        client=client,
        max_attempts=2,
    )

    assert state.error is None
    assert state.attempts == 2
    assert state.retrieved_tables is None  # retrieval never ran
