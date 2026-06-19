"""Thinnest generate→execute loop (issue 4) — CI-safe unit coverage.

No network and no Postgres here: ``generate`` is exercised with an injected fake
Anthropic client, and ``execute``/``run_pipeline`` run against an in-memory
SQLite engine. Correctness against gold is asserted by the harness in issue 5;
this file guards the wiring, the prompt-template externalization, and the
SQL-extraction/PII-logging behavior.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from nl2sql.llm import LLMResponse
from nl2sql.pipeline.execute import execute
from nl2sql.pipeline.generate import (
    _extract_sql,
    generate,
    render_prompt,
)
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState
from nl2sql.prompts import GENERATE_TEMPLATE, PROMPTS_DIR


class FakeLLMClient:
    """An ``nl2sql.llm.LLMClient`` stand-in that echoes canned SQL responses.

    Implements the one-method ``complete`` seam the pipeline depends on, so tests
    run without LiteLLM, a network, or an API key. ``reply`` may be a single
    string (returned every call) or a list consumed one reply per call — the
    latter drives the self-correction loop in tests (a broken first attempt, a
    good second one). The last reply repeats once the list is spent, so an
    over-eager loop never raises here. Each call is recorded under ``calls`` in
    the ``{"messages": [{"content": prompt}], ...}`` shape the assertions read.
    """

    def __init__(self, reply: str | list[str]) -> None:
        self.replies = [reply] if isinstance(reply, str) else list(reply)
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LLMResponse:
        self.calls.append(
            {
                "messages": [{"role": "user", "content": prompt}],
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        text = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return LLMResponse(text=text, input_tokens=11, output_tokens=7)


@pytest.fixture
def sqlite_engine():
    """In-memory SQLite with a tiny users table — a Postgres stand-in for tests."""
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, country TEXT)"))
        conn.execute(text("INSERT INTO users VALUES (1, 'US'), (2, 'US'), (3, 'ES')"))
    return engine


# --- prompt externalization -------------------------------------------------


def test_generate_template_is_externalized_in_prompts_dir():
    assert (PROMPTS_DIR / GENERATE_TEMPLATE).is_file()


def test_render_prompt_inlines_schema_and_question():
    rendered = render_prompt(schema="CREATE TABLE t (id INT);", question="how many?")
    assert "CREATE TABLE t (id INT);" in rendered
    assert "how many?" in rendered


# --- SQL extraction ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("SELECT 1;", "SELECT 1;"),
        ("  SELECT 1;  ", "SELECT 1;"),
        ("```sql\nSELECT 1;\n```", "SELECT 1;"),
        ("```\nSELECT 1;\n```", "SELECT 1;"),
        ("```SQL\nSELECT 1;\n```", "SELECT 1;"),
    ],
)
def test_extract_sql_strips_fences_and_whitespace(raw, expected):
    assert _extract_sql(raw) == expected


# --- generate stage ---------------------------------------------------------


def test_generate_sets_candidate_sql_via_injected_client():
    state = RunState(question="how many users?", db_id="payments")
    client = FakeLLMClient(reply="```sql\nSELECT count(*) FROM users;\n```")

    generate(state, schema="CREATE TABLE users (id INT);", client=client)

    assert state.candidate_sql == "SELECT count(*) FROM users;"
    # The rendered prompt (schema + question) reached the model.
    sent = client.calls[0]["messages"][0]["content"]
    assert "CREATE TABLE users (id INT);" in sent
    assert "how many users?" in sent


# --- execute stage ----------------------------------------------------------


def test_execute_populates_rows_and_columns(sqlite_engine):
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = (
        "SELECT country, count(*) AS n FROM users GROUP BY country ORDER BY country"
    )

    execute(state, sqlite_engine)

    assert state.error is None
    assert state.result_columns == ["country", "n"]
    assert state.result_rows == [("ES", 1), ("US", 2)]


def test_execute_captures_error_without_raising(sqlite_engine):
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "SELECT * FROM does_not_exist"

    execute(state, sqlite_engine)

    assert state.error is not None
    assert state.result_rows is None


def test_execute_handles_missing_sql(sqlite_engine):
    state = RunState(question="q", db_id="payments")
    execute(state, sqlite_engine)
    assert state.error == "no candidate SQL to execute"


# --- linear wiring ----------------------------------------------------------


def test_run_pipeline_wires_generate_then_execute(sqlite_engine):
    client = FakeLLMClient(reply="SELECT count(*) AS n FROM users WHERE country = 'US'")

    state = run_pipeline(
        "how many US users?",
        schema="CREATE TABLE users (id INT, country TEXT);",
        engine=sqlite_engine,
        client=client,
    )

    assert state.candidate_sql == "SELECT count(*) AS n FROM users WHERE country = 'US'"
    assert state.result_columns == ["n"]
    assert state.result_rows == [(2,)]
    assert state.error is None


def test_execute_does_not_log_raw_rows(sqlite_engine, caplog):
    """Obs contract: row data never reaches logs — only the shape (CLAUDE.md §5.3)."""
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "SELECT country FROM users"

    with caplog.at_level("INFO", logger="nl2sql"):
        execute(state, sqlite_engine)

    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "row_count" in log_text
    assert "ES" not in log_text  # an actual cell value must not appear


# --- correct stage ----------------------------------------------------------


def test_correct_stages_failure_and_clears_it_for_retry():
    from nl2sql.pipeline.correct import correct

    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "SELECT * FROM nope"
    state.error = "no such table: nope"

    correct(state)

    assert state.correction == {
        "sql": "SELECT * FROM nope",
        "error": "no such table: nope",
    }
    # The failed attempt is cleared so the next cycle is scored on its own outcome.
    assert state.error is None
    assert state.result_rows is None
    assert state.result_columns is None


def test_correct_is_a_noop_without_an_error():
    from nl2sql.pipeline.correct import correct

    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "SELECT 1"

    correct(state)

    assert state.correction is None  # nothing to feed back; never fabricated


def test_correction_feeds_prior_sql_and_error_into_render():
    state = RunState(question="q", db_id="payments")
    state.correction = {"sql": "SELECT * FROM nope", "error": "no such table: nope"}
    prompt = render_prompt(
        schema="CREATE TABLE t (id INT);", question="q", correction=state.correction
    )
    assert "SELECT * FROM nope" in prompt
    assert "no such table: nope" in prompt


def test_render_prompt_without_correction_matches_v2_shape():
    # Correction off → the block is omitted entirely (pass@1 prompt unchanged).
    prompt = render_prompt(schema="CREATE TABLE t (id INT);", question="q")
    assert "previous attempt" not in prompt.lower()
    # The v3 bump is a no-op when correction is off (the PR's pass@1-invariance
    # claim): the prompt ends at the question with no trailing correction
    # whitespace, so prompt-CI sees no behavioral diff vs v2.
    assert prompt.endswith("Question:\nq\n")


# --- the capped self-correction loop ----------------------------------------


def test_loop_recovers_within_budget(sqlite_engine):
    # A broken first attempt, a good second one: the loop feeds the error back and
    # recovers inside the budget — the pass@1→pass@k story in miniature.
    client = FakeLLMClient(
        reply=[
            "SELECT count(*) AS n FROM nonexistent_table",  # attempt 1 errors
            "SELECT count(*) AS n FROM users WHERE country = 'US'",  # attempt 2 ok
        ]
    )

    state = run_pipeline(
        "how many US users?",
        schema="CREATE TABLE users (id INT, country TEXT);",
        engine=sqlite_engine,
        client=client,
        max_attempts=2,
    )

    assert state.error is None
    assert state.attempts == 2
    assert state.result_rows == [(2,)]
    # The second generate saw the first attempt's failure (error fed back).
    retry_prompt = client.calls[1]["messages"][0]["content"]
    assert "nonexistent_table" in retry_prompt
    assert "no such table" in retry_prompt.lower()


def test_loop_exhausts_budget_when_never_recovering(sqlite_engine):
    client = FakeLLMClient(reply="SELECT count(*) AS n FROM nonexistent_table")

    state = run_pipeline(
        "broken",
        schema="CREATE TABLE users (id INT);",
        engine=sqlite_engine,
        client=client,
        max_attempts=3,
    )

    assert state.error is not None
    assert state.attempts == 3  # spent the whole budget
    assert len(client.calls) == 3


def test_single_shot_default_makes_one_attempt(sqlite_engine):
    # Default budget is 1: no correction, exactly one generate — pass@1 mode.
    client = FakeLLMClient(reply="SELECT count(*) AS n FROM nonexistent_table")

    state = run_pipeline(
        "broken",
        schema="CREATE TABLE users (id INT);",
        engine=sqlite_engine,
        client=client,
    )

    assert state.error is not None
    assert state.attempts == 1
    assert len(client.calls) == 1


def test_high_budget_passk_does_not_trip_langgraph_recursion_limit(sqlite_engine):
    # Regression guard for the Step-7 LangGraph swap: each attempt costs ~4
    # supersteps (generate → guard → execute → correct), so a high pass@k budget
    # must scale the graph's recursion ceiling (run_pipeline sets
    # recursion_limit = budget * 6 + 25). A never-recovering budget of 8 needs a
    # ceiling of ~33 — above LangGraph's *default* of 25 — so it would raise
    # GraphRecursionError if the ceiling weren't sized to the budget. The
    # guard-passing count(*) SQL reaches execute every attempt (a SELECT * would be
    # rejected pre-execution and end at attempt 1). Asserting the whole budget is
    # spent proves the loop runs to exhaustion, not cut short by the framework.
    client = FakeLLMClient(reply="SELECT count(*) AS n FROM nonexistent_table")

    state = run_pipeline(
        "broken",
        schema="CREATE TABLE users (id INT);",
        engine=sqlite_engine,
        client=client,
        max_attempts=8,
    )

    assert state.error is not None
    assert state.attempts == 8  # full budget spent, no premature recursion cutoff
    assert len(client.calls) == 8
