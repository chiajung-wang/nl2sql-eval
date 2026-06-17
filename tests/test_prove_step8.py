"""Step 8 DoD: a failing question is diagnosable from its trace (offline).

Captures the retry-exhausted trace via ``eval.prove_step8`` (no live model, no
Langfuse keys) and asserts the per-span stage detail the "done when" calls for is
all present — retrieved tables, generated SQL, guard verdict, attempts, the
execution error, the terminal state — and that no raw PII rides on the trace.
"""

from __future__ import annotations

from eval.prove_step8 import capture_failing_trace, render_html
from nl2sql.pipeline.state import TerminalState


def _spans_named(trace, name):
    return [s for s in trace.root.walk() if s.name == name]


def test_failing_question_is_retry_exhausted_with_two_attempts():
    trace = capture_failing_trace()
    assert trace.terminal is TerminalState.RETRY_EXHAUSTED
    assert trace.state.attempts == 2


def test_trace_is_one_tree_rooted_at_pipeline():
    trace = capture_failing_trace()
    assert trace.root.name == "pipeline"
    # Every stage span is a descendant of the single root — one run, one trace.
    names = {s.name for s in trace.root.walk()}
    assert {"retrieve", "generate", "guard", "execute", "correct", "redact"} <= names


def test_each_stage_span_shows_its_detail():
    trace = capture_failing_trace()
    # retrieve → which tables it selected
    retrieves = _spans_named(trace, "retrieve")
    assert retrieves and retrieves[0].output["retrieved_tables"]
    # generate → the candidate SQL (one span per attempt)
    generates = _spans_named(trace, "generate")
    assert len(generates) == 2
    assert all(g.output["candidate_sql"] for g in generates)
    assert all(g.as_type == "generation" for g in generates)
    # guard → the verdict
    guards = _spans_named(trace, "guard")
    assert guards and guards[0].output["decision"] == "allow"
    # execute → the failure, surfaced as the exception class and an ERROR level
    executes = _spans_named(trace, "execute")
    assert executes and executes[0].output["error"] == "OperationalError"


def test_redact_span_present_on_a_failed_run_with_no_result():
    trace = capture_failing_trace()
    redacts = _spans_named(trace, "redact")
    # A failed run has nothing to present — the redact span records that.
    assert redacts and redacts[0].output.get("presented") is False


def test_no_raw_pii_anywhere_on_the_trace():
    trace = capture_failing_trace()
    rendered = render_html(trace)
    blob = "\n".join(str(s.output) for s in trace.root.walk()) + rendered
    for secret in ("alice@secret.example", "Alice Lee"):
        assert secret not in blob
