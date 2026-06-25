"""The demo's testable core — the wrapper made visible, without Streamlit.

``apps.demo.runner.run_demo`` drives the **import-shared** pipeline and the
**harness** classifier, so these tests double as proof that the demo can't drift
from what the eval measures. No Streamlit, no network, no API key: an injected
fake client and an in-memory SQLite db stand in. The load-bearing assertions are
that the view surfaces the wrapper (guard decision, retry count, cost, terminal
state) and that it exposes **only the presented (redacted) result** — never the
raw verified rows the harness scores (CLAUDE.md §3/§5).
"""

from __future__ import annotations

from dataclasses import fields

import pytest
from sqlalchemy import create_engine, text

from apps.demo.runner import (
    STATE_BADGES,
    DemoView,
    badge_for,
    parse_dataset,
    run_demo,
)
from nl2sql.llm import LLMResponse
from nl2sql.pipeline.redact import MASK, NO_REDACTION, RedactionPolicy
from nl2sql.pipeline.state import TerminalState

# A schema whose ``email`` column the DDL marks as PII — drives redaction.
SCHEMA = """\
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    country TEXT,
    email TEXT  -- PII
);
"""


class FakeLLMClient:
    """Echoes canned SQL — the one-method ``complete`` seam, no network/key."""

    def __init__(self, reply: str | list[str]) -> None:
        self.replies = [reply] if isinstance(reply, str) else list(reply)
        self.calls = 0

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LLMResponse:
        text_ = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return LLMResponse(text=text_, input_tokens=11, output_tokens=7)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", future=True)
    with eng.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, country TEXT, email TEXT)"
            )
        )
        conn.execute(
            text("INSERT INTO users VALUES (1, 'US', 'a@x.com'), (2, 'ES', 'b@y.com')")
        )
    return eng


def _run(engine, reply, **kw):
    return run_demo(
        "How many US users?",
        engine=engine,
        schema=SCHEMA,
        db_id="demo",
        dialect="SQLite",
        model="anthropic/claude-sonnet-4-6",
        client=FakeLLMClient(reply),
        **kw,
    )


def test_clean_run_surfaces_the_wrapper(engine):
    view = _run(engine, "SELECT id, country FROM users WHERE country = 'US'")
    assert isinstance(view, DemoView)
    assert view.terminal_state == "success"
    assert view.guard_allowed is True
    assert view.attempts == 1
    # Cost is priced from the dated list table for a known model.
    assert view.list_cost_usd is not None and view.list_cost_usd > 0
    assert view.input_tokens > 0 and view.output_tokens > 0
    assert view.presented_rows == [(1, "US")]


def test_presented_result_is_redacted_and_raw_is_never_exposed(engine):
    # The PII column (email) is masked on the presented exit, and the view has no
    # field that could carry the raw verified rows at all.
    view = _run(
        engine,
        "SELECT id, email FROM users WHERE id = 1",
        redaction_policy=RedactionPolicy.from_ddl(SCHEMA),
    )
    assert view.presented_columns == ["id", "email"]
    assert view.presented_rows == [(1, MASK)]
    assert "a@x.com" not in {v for row in view.presented_rows for v in row}
    field_names = {f.name for f in fields(DemoView)}
    assert "result_rows" not in field_names and "result_columns" not in field_names


def test_guardrail_rejection_is_revealed_not_executed(engine):
    view = _run(engine, "DELETE FROM users")
    assert view.guard_allowed is False
    assert view.terminal_state == "guardrail_rejected"
    assert view.guard_rule  # the rule that fired is surfaced
    assert view.presented_rows is None  # never executed → nothing to present


def test_retry_count_reflects_the_correction_loop(engine):
    # A broken first attempt, a good second one: the loop recovers within budget
    # and the view shows the retry count actually moved.
    view = _run(
        engine,
        # First attempt passes the guard (explicit column, a real SELECT) but
        # errors at execution (no such table); the loop feeds the error back.
        [
            "SELECT id FROM nonexistent_table",
            "SELECT id FROM users WHERE country = 'US'",
        ],
        max_attempts=2,
    )
    assert view.terminal_state == "success"
    assert view.attempts == 2


def test_no_redaction_policy_passes_values_through(engine):
    view = _run(
        engine, "SELECT country FROM users WHERE id = 1", redaction_policy=NO_REDACTION
    )
    assert view.presented_rows == [("US",)]


# --- the shell's pure glue (testable without Streamlit) ---------------------


def test_every_terminal_state_has_a_badge():
    # A new terminal state can't ship unstyled — the demo would render a blank
    # badge. Asserting full coverage here catches that at test time.
    for state in TerminalState:
        assert state.value in STATE_BADGES
        emoji, level = badge_for(state.value)
        assert emoji and level in {"ok", "warn", "error", "info"}


def test_badge_for_unknown_state_falls_back():
    assert badge_for("not_a_state") == ("•", "info")


def test_parse_dataset_resolves_payments_and_bird():
    assert parse_dataset("payments") == ("payments", "payments", "PostgreSQL")
    assert parse_dataset("bird/financial") == ("bird", "financial", "SQLite")


def test_parse_dataset_rejects_unknown_choice():
    with pytest.raises(ValueError):
        parse_dataset("mysql/whatever")
    with pytest.raises(ValueError):
        parse_dataset("bird/")  # no db id


def test_app_imports_under_streamlit_path_model():
    # Streamlit runs app.py as a script with apps/demo/ (not the repo root) on
    # sys.path, so the repo-root peers `apps`/`eval` are unimportable unless the
    # app bootstraps the path itself. Reproduce that exact path model and exec the
    # module body (main() is guarded, so it does not run). Skips when the demo
    # group isn't installed — the core suite stays streamlit-free.
    import os
    import subprocess
    import sys
    from pathlib import Path

    pytest.importorskip("streamlit")
    repo = Path(__file__).resolve().parents[1]
    app = repo / "apps" / "demo" / "app.py"
    code = (
        "import sys;"
        f"sys.path[:] = [p for p in sys.path if p not in ('', {str(repo)!r})];"
        f"sys.path.insert(0, {str(app.parent)!r});"
        f"ns = {{'__name__': 'appmod', '__file__': {str(app)!r}}};"
        f"exec(compile(open({str(app)!r}).read(), {str(app)!r}, 'exec'), ns)"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr
