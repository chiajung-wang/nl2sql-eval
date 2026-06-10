"""Thinnest generate→execute loop (issue 4) — CI-safe unit coverage.

No network and no Postgres here: ``generate`` is exercised with an injected fake
Anthropic client, and ``execute``/``run_pipeline`` run against an in-memory
SQLite engine. Correctness against gold is asserted by the harness in issue 5;
this file guards the wiring, the prompt-template externalization, and the
SQL-extraction/PII-logging behavior.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from nl2sql.pipeline.execute import execute
from nl2sql.pipeline.generate import (
    GENERATE_TEMPLATE,
    PROMPTS_DIR,
    _extract_sql,
    generate,
    render_prompt,
)
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState


class FakeAnthropic:
    """Stand-in for ``anthropic.Anthropic`` that echoes a canned SQL response."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self.reply)],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        )


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
    client = FakeAnthropic(reply="```sql\nSELECT count(*) FROM users;\n```")

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
    client = FakeAnthropic(reply="SELECT count(*) AS n FROM users WHERE country = 'US'")

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
