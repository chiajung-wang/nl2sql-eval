"""Smoke test: the full PRD §8 module tree imports, and state.py is well-formed.

Guards the Step 1 acceptance criteria — every stubbed module resolves, and the
terminal-state enum carries its complete, frozen set of values.
"""

import importlib

import pytest

PIPELINE_MODULES = [
    "nl2sql",
    "nl2sql.pipeline",
    "nl2sql.pipeline.graph",
    "nl2sql.pipeline.state",
    "nl2sql.pipeline.retrieve",
    "nl2sql.pipeline.generate",
    "nl2sql.pipeline.guard",
    "nl2sql.pipeline.execute",
    "nl2sql.pipeline.correct",
    "nl2sql.pipeline.redact",
    "nl2sql.schema_index",
    "nl2sql.llm",
    "nl2sql.obs",
]

EVAL_MODULES = [
    "eval",
    "eval.harness",
    "eval.compare",
    "eval.metrics",
    "eval.datasets",
    "eval.datasets.bird",
    "eval.datasets.payments",
    "apps.demo",
]


@pytest.mark.parametrize("module", PIPELINE_MODULES + EVAL_MODULES)
def test_module_imports(module: str) -> None:
    importlib.import_module(module)


def test_terminal_state_is_complete() -> None:
    from nl2sql.pipeline.state import TerminalState

    assert {s.value for s in TerminalState} == {
        "success",
        "wrong_answer",
        "retry_exhausted",
        "execution_error_final",
        "guardrail_rejected",
        "retrieval_empty",
    }


def test_run_state_minimal_construction() -> None:
    from nl2sql.pipeline.state import RunState

    state = RunState(question="how many users?", db_id="payments")
    assert state.attempts == 0
    assert state.terminal_state is None
    assert state.meta == {}


def test_obs_stage_span_yields_attachable_dict() -> None:
    from nl2sql.obs import stage_span

    with stage_span("generate", db_id="payments") as extra:
        extra["candidate_sql"] = "SELECT 1"
    assert extra["candidate_sql"] == "SELECT 1"
