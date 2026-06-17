"""Redact stage + redacted-logging enforcement (Step 8, issue #55).

Two things are proven here, offline:

1. ``redact`` is deterministic, schema-driven, column-aware PII masking that
   produces the **presented exit** without touching the **raw exit** the harness
   scores (the two-exit discipline, CLAUDE.md §3/§5.2).
2. End-to-end, **raw PII never reaches a Langfuse span or a log line** — asserted
   by running the full pipeline over a table with real PII while capturing every
   span field (via an injected fake recorder) and every log record, then scanning
   them for the secret value.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text

from nl2sql import obs
from nl2sql.llm import LLMResponse
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.redact import MASK, NO_REDACTION, RedactionPolicy, redact
from nl2sql.pipeline.state import RunState

# A tiny DDL fragment in the payments style: a trailing ``-- PII`` marks a column.
PII_DDL = """
CREATE TABLE users (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,   -- PII
    full_name   TEXT NOT NULL,          -- PII
    phone       TEXT,                   -- PII
    country     CHAR(2) NOT NULL,
    brand       TEXT                    -- e.g. visa (PII-adjacent)
);
"""

SECRET_EMAIL = "alice@secret.example"


# --- policy parsing ----------------------------------------------------------


def test_policy_from_ddl_picks_up_marked_columns():
    policy = RedactionPolicy.from_ddl(PII_DDL)
    assert policy.pii_columns == {"email", "full_name", "phone"}


def test_policy_excludes_pii_adjacent_and_unmarked():
    policy = RedactionPolicy.from_ddl(PII_DDL)
    # ``brand`` is labelled PII-adjacent (deliberately weaker) — not masked.
    assert "brand" not in policy.pii_columns
    assert "country" not in policy.pii_columns


def test_pii_indices_are_name_based_and_alias_insensitive():
    policy = RedactionPolicy.from_ddl(PII_DDL)
    assert policy.pii_indices(["email", "country"]) == [0]
    # Normalization: case + quotes don't dodge the policy.
    assert policy.pii_indices(['"Email"', "Country"]) == [0]


# --- masking -----------------------------------------------------------------


def _state_with_result() -> RunState:
    s = RunState(question="q", db_id="payments")
    s.result_columns = ["email", "country"]
    s.result_rows = [(SECRET_EMAIL, "US"), ("bob@secret.example", "ES")]
    return s


def test_redact_masks_pii_and_leaves_raw_exit_untouched():
    state = _state_with_result()
    policy = RedactionPolicy.from_ddl(PII_DDL)
    redact(state, policy)

    # Presented exit: PII column blanked with the fixed mask, non-PII passed through.
    assert state.presented_columns == ["email", "country"]
    assert state.presented_rows == [(MASK, "US"), (MASK, "ES")]
    # Raw exit: pristine — the harness still scores the real values (§5.2).
    assert state.result_rows == [(SECRET_EMAIL, "US"), ("bob@secret.example", "ES")]


def test_redact_aliased_pii_is_a_known_limitation():
    """Pin the deliberate gap: a PII column aliased to a non-PII name escapes.

    Masking is on the *output* column name, so ``SELECT email AS contact`` yields a
    column named ``contact`` that the policy doesn't recognize. Documented in
    ``RedactionPolicy``; closing it needs sqlglot projection resolution (deeper than
    this stage). This test makes the trade-off conscious rather than silent — if a
    later change masks it, update the docstring too.
    """
    state = RunState(question="q", db_id="payments")
    state.result_columns = ["contact"]  # email aliased AS contact
    state.result_rows = [(SECRET_EMAIL,)]
    redact(state, RedactionPolicy.from_ddl(PII_DDL))
    # Current behavior: the aliased PII value is NOT masked.
    assert state.presented_rows == [(SECRET_EMAIL,)]


def test_redact_without_pii_columns_copies_through():
    state = _state_with_result()
    redact(state, NO_REDACTION)  # empty policy masks nothing (the BIRD path)
    assert state.presented_rows == state.result_rows
    # A copy, not an alias — presenting must never mutate the raw exit later.
    assert state.presented_rows is not state.result_rows


def test_redact_noop_when_no_result():
    """An errored/guard-rejected run has nothing to present — presented stays None."""
    state = RunState(question="q", db_id="payments")
    state.error = "boom"
    redact(state, RedactionPolicy.from_ddl(PII_DDL))
    assert state.presented_rows is None and state.presented_columns is None


# --- end-to-end: raw PII never reaches spans or logs -------------------------


class _FakeObservation:
    def __init__(self, name, metadata):
        self.name = name
        self.metadata = metadata
        self.update_kwargs: dict = {}

    def update(self, **kwargs):
        self.update_kwargs = kwargs


class _FakeLangfuse:
    """Captures every span's creation metadata and update payload for scanning."""

    def __init__(self):
        self.observations: list[_FakeObservation] = []

    @contextmanager
    def start_as_current_observation(self, *, name, as_type, metadata=None, **_):
        ob = _FakeObservation(name, metadata or {})
        self.observations.append(ob)
        yield ob

    def all_text(self) -> str:
        return json.dumps(
            [(o.name, o.metadata, o.update_kwargs) for o in self.observations],
            default=str,
        )


class _FakeLLMClient:
    def __init__(self, sql: str):
        self.sql = sql

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LLMResponse:
        return LLMResponse(text=self.sql, input_tokens=5, output_tokens=3)


@pytest.fixture
def pii_engine():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (email TEXT, country TEXT)"))
        conn.execute(text(f"INSERT INTO users VALUES ('{SECRET_EMAIL}', 'US')"))
    return engine


def test_pipeline_redacts_presented_exit_and_keeps_raw(pii_engine):
    state = run_pipeline(
        "list emails",
        schema=PII_DDL,
        engine=pii_engine,
        dialect="sqlite",
        client=_FakeLLMClient("SELECT email, country FROM users"),
        redaction_policy=RedactionPolicy.from_ddl(PII_DDL),
    )
    # Raw exit holds the real PII (so the harness can score it); presented masks it.
    assert state.result_rows == [(SECRET_EMAIL, "US")]
    assert state.presented_rows == [(MASK, "US")]


def test_raw_pii_never_reaches_spans_or_logs(pii_engine, caplog):
    fake = _FakeLangfuse()
    obs.set_client(fake)
    try:
        with caplog.at_level("INFO", logger="nl2sql"):
            state = run_pipeline(
                "list emails",
                schema=PII_DDL,
                engine=pii_engine,
                dialect="sqlite",
                client=_FakeLLMClient("SELECT email, country FROM users"),
                redaction_policy=RedactionPolicy.from_ddl(PII_DDL),
            )
        log_text = "\n".join(r.getMessage() for r in caplog.records)
    finally:
        obs.reset_client()

    # The run really did read the PII (proving the assertion isn't vacuous)...
    assert state.result_rows == [(SECRET_EMAIL, "US")]
    # ...yet the secret appears in neither the spans nor the logs.
    assert SECRET_EMAIL not in fake.all_text()
    assert SECRET_EMAIL not in log_text
    # A redact span ran and recorded *which* column it masked (a name, not a value).
    redact_spans = [o for o in fake.observations if o.name == "redact"]
    assert redact_spans and redact_spans[0].update_kwargs["output"][
        "redacted_columns"
    ] == ["email"]
