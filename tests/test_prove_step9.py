"""The Step-9 proof asserts a caught regression from the committed reports.

Offline and deterministic (defer-API-key): it replays the captured live reports
under ``docs/plans/step-9/prompt-ci-demo/`` — no model, no network. These tests
lock that the committed artifacts still encode a real, caught regression and that
the proof's verdict logic is correct in both directions.
"""

from __future__ import annotations

from eval.prompt_ci import PromptRunReport
from eval.prove_step9 import BASE_REPORT, HEAD_REPORT, prove


def test_committed_reports_encode_a_real_caught_regression():
    base = PromptRunReport.read_json(BASE_REPORT)
    head = PromptRunReport.read_json(HEAD_REPORT)
    # A real prompt change (distinct fingerprints) ...
    assert base.prompt_fingerprint != head.prompt_fingerprint
    # ... that the gate sees as a drop on the frozen slice.
    assert head.pass_at_1 < base.pass_at_1
    assert base.slice_name == head.slice_name == "step9-prompt-ci"


def test_prove_returns_zero_on_the_committed_caught_regression():
    assert prove() == 0


def test_prove_fails_when_head_is_not_a_regression(tmp_path):
    # Guard the verdict logic: an improvement (or no drop) must NOT be reported as
    # a caught regression — otherwise the proof would rubber-stamp anything.
    base = PromptRunReport.read_json(BASE_REPORT)
    better = PromptRunReport(
        prompt_version="generate/v9",
        prompt_fingerprint="sha256:better",
        model=base.model,
        slice_name=base.slice_name,
        k=base.k,
        total=base.total,
        n_correct_1=base.total,  # everything passes
        n_correct_k=base.total,
    )
    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base.write_json(base_path)
    better.write_json(head_path)
    assert prove(base_path, head_path) == 1
