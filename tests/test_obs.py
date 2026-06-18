"""Observability seam — offline-provable Langfuse wiring (Step 8, issue #54).

No network and no Langfuse keys: a fake recorder is injected via
``obs.set_client`` to capture the observations ``stage_span`` opens, and the
no-Langfuse path is asserted to be pure structured logging (the default, and how
CI runs). The fake mirrors the langfuse-4.x context-manager API
(``start_as_current_observation`` → an observation with ``.update``), including
the automatic parent/child nesting that makes one run a single trace.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from nl2sql import obs


class FakeObservation:
    """A recorded Langfuse observation: its creation args and ``.update`` payload."""

    def __init__(
        self,
        name: str,
        as_type: str,
        metadata: dict,
        parent: FakeObservation | None,
        input: object = None,
    ):
        self.name = name
        self.as_type = as_type
        self.metadata = metadata
        self.parent = parent
        self.input = input
        self.update_kwargs: dict | None = None

    def update(self, **kwargs):
        self.update_kwargs = kwargs


class FakeLangfuse:
    """Minimal stand-in for the Langfuse client used by ``obs.stage_span``.

    Records every observation in creation order and tracks the active observation
    so children nest under their enclosing span — exactly the trace shape the real
    OpenTelemetry-backed client builds.
    """

    def __init__(self):
        self.observations: list[FakeObservation] = []
        self._stack: list[FakeObservation] = []
        self.flushed = 0

    @contextmanager
    def start_as_current_observation(
        self, *, name, as_type, metadata=None, input=None, **_
    ):
        parent = self._stack[-1] if self._stack else None
        ob = FakeObservation(name, as_type, metadata or {}, parent, input=input)
        self.observations.append(ob)
        self._stack.append(ob)
        try:
            yield ob
        finally:
            self._stack.pop()

    def flush(self):
        self.flushed += 1


@pytest.fixture
def fake_client():
    fake = FakeLangfuse()
    obs.set_client(fake)
    try:
        yield fake
    finally:
        obs.reset_client()


# --- offline / no-op path ----------------------------------------------------


def test_get_client_is_none_without_keys(monkeypatch):
    """The default (no Langfuse keys) resolves to None — no client, no network."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    obs.reset_client()
    assert obs.get_client() is None
    obs.reset_client()


def test_stage_span_is_log_only_without_client(caplog):
    """With no client, ``stage_span`` is exactly the prior structured-logging seam."""
    obs.set_client(None)
    try:
        with caplog.at_level("INFO", logger="nl2sql"):
            with obs.stage_span("execute", db_id="payments") as extra:
                extra["row_count"] = 3
        events = [json.loads(r.getMessage()) for r in caplog.records]
    finally:
        obs.reset_client()
    assert [e["event"] for e in events] == ["start", "end"]
    end = events[-1]
    assert end["stage"] == "execute" and end["row_count"] == 3
    assert "duration_ms" in end


def test_flush_is_noop_without_client():
    obs.set_client(None)
    try:
        obs.flush()  # must not raise
    finally:
        obs.reset_client()


# --- wired path (fake client) ------------------------------------------------


def test_stage_span_opens_observation_with_safe_fields(fake_client):
    with obs.stage_span("execute", db_id="payments") as extra:
        extra["row_count"] = 5
        extra["column_count"] = 2

    (ob,) = fake_client.observations
    assert ob.name == "execute"
    assert ob.as_type == "span"
    assert ob.metadata == {"db_id": "payments"}
    # The yielded result dict folds into the span output, with a duration.
    assert ob.update_kwargs["output"] == {"row_count": 5, "column_count": 2}
    assert "duration_ms" in ob.update_kwargs["metadata"]


def test_generation_span_promotes_tokens_and_cost(fake_client):
    with obs.stage_span(
        "generate", as_type="generation", db_id="payments", model="claude-x"
    ) as extra:
        extra["candidate_sql"] = "SELECT 1"
        extra["input_tokens"] = 11
        extra["output_tokens"] = 7
        extra["cost_usd"] = 0.0021

    (ob,) = fake_client.observations
    assert ob.as_type == "generation"
    # Tokens/cost are promoted to Langfuse's native axes, not just metadata.
    assert ob.update_kwargs["usage_details"] == {"input": 11, "output": 7}
    assert ob.update_kwargs["cost_details"] == {"total": 0.0021}
    assert ob.update_kwargs["model"] == "claude-x"
    # The SQL still rides in the output payload.
    assert ob.update_kwargs["output"]["candidate_sql"] == "SELECT 1"


def test_nested_spans_form_one_trace(fake_client):
    """A run = one trace: stage spans entered inside ``pipeline`` nest under it."""
    with obs.stage_span("pipeline", db_id="payments"):
        with obs.stage_span("generate", as_type="generation", db_id="payments"):
            pass
        with obs.stage_span("execute", db_id="payments"):
            pass

    by_name = {o.name: o for o in fake_client.observations}
    assert by_name["pipeline"].parent is None
    assert by_name["generate"].parent is by_name["pipeline"]
    assert by_name["execute"].parent is by_name["pipeline"]


def test_raising_stage_marks_span_errored_and_reraises(fake_client):
    """A stage that raises stays diagnosable: span level=ERROR, exception re-raised."""
    with pytest.raises(ValueError):
        with obs.stage_span("execute", db_id="payments") as extra:
            extra["row_count"] = 0
            raise ValueError("boom")

    (ob,) = fake_client.observations
    assert ob.update_kwargs["level"] == "ERROR"
    # The exception *class* is recorded — never its message (which could echo PII).
    assert ob.update_kwargs["status_message"] == "ValueError"


def test_raising_stage_logs_error_class_without_client(caplog):
    """Even with no Langfuse, the stage-end log records the exception class."""
    obs.set_client(None)
    try:
        with caplog.at_level("INFO", logger="nl2sql"):
            with pytest.raises(RuntimeError):
                with obs.stage_span("guard", db_id="payments"):
                    raise RuntimeError("nope")
        end = json.loads(caplog.records[-1].getMessage())
    finally:
        obs.reset_client()
    assert end["event"] == "end" and end["error"] == "RuntimeError"


def test_span_update_failure_never_breaks_the_stage(fake_client):
    """A Langfuse hiccup on update is swallowed — obs is a seam, not a dependency."""

    class Boom(FakeObservation):
        def update(self, **kwargs):
            raise RuntimeError("langfuse down")

    @contextmanager
    def boom_observation(*, name, as_type, metadata=None, **_):
        yield Boom(name, as_type, metadata or {}, None)

    fake_client.start_as_current_observation = boom_observation
    # The body still runs and returns normally despite the failing span update.
    with obs.stage_span("execute", db_id="payments") as extra:
        extra["row_count"] = 1
    assert extra["row_count"] == 1


# --- trace-level input/output and attributes ---------------------------------


def test_trace_input_is_recorded_on_the_root_observation(fake_client):
    """The root span's ``trace_input`` (the NL question) is set on the observation.

    In v4 the root observation's input becomes the trace input — what makes a run
    readable at a glance: question in, result-shape out.
    """
    with obs.stage_span(
        "pipeline", trace_input="How many users are from the US?", db_id="payments"
    ) as extra:
        extra["presented_row_count"] = 1

    (ob,) = fake_client.observations
    assert ob.input == "How many users are from the US?"
    assert ob.update_kwargs["output"] == {"presented_row_count": 1}


def test_stage_span_omits_input_when_not_given(fake_client):
    """A normal stage passes no ``input`` — only the root span opts in."""
    with obs.stage_span("execute", db_id="payments"):
        pass
    (ob,) = fake_client.observations
    assert ob.input is None


def test_trace_attributes_is_noop_without_client():
    """Offline (no client), ``trace_attributes`` is a pure pass-through."""
    obs.set_client(None)
    try:
        with obs.trace_attributes(trace_name="nl2sql", tags=["db:x"]):
            pass  # must not raise, must not touch langfuse
    finally:
        obs.reset_client()


def test_trace_attributes_propagates_only_set_fields(fake_client, monkeypatch):
    """When wired, only the non-None attributes reach ``propagate_attributes``."""
    import langfuse

    captured: dict = {}

    @contextmanager
    def fake_propagate(**kwargs):
        captured.update(kwargs)
        yield

    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate)

    with obs.trace_attributes(
        trace_name="nl2sql",
        session_id="run-2026-06-18",
        tags=["db:payments", "model:claude-x"],
    ):
        pass

    assert captured == {
        "trace_name": "nl2sql",
        "session_id": "run-2026-06-18",
        "tags": ["db:payments", "model:claude-x"],
    }


def test_trace_attributes_survives_a_langfuse_failure(fake_client, monkeypatch):
    """A failing ``propagate_attributes`` degrades to a pass-through, never raises."""
    import langfuse

    def boom(**_):
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(langfuse, "propagate_attributes", boom)

    with obs.trace_attributes(trace_name="nl2sql"):
        pass  # the run continues despite the obs failure
