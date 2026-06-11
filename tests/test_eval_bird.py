"""BIRD runner + dialect-aware prompt (Step 3, Issue 3).

The prompt-threading and the RESULTS.md row/append logic are tested offline (no
API, no BIRD download). ``build_bird_cases`` executes only gold SQL (SQLite, no
API), so it is tested whenever the BIRD data is present and skipped otherwise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eval import eval_bird
from eval.datasets.bird.loader import bird_data_dir
from eval.metrics import BatchReport, CaseResult
from nl2sql.pipeline.generate import PROMPT_VERSION, generate, render_prompt
from nl2sql.pipeline.state import RunState, TerminalState

# --- dialect-aware prompt (offline) ----------------------------------------


def test_render_prompt_names_the_dialect():
    assert "SQLite" in render_prompt("SCHEMA", "Q?", dialect="SQLite")
    assert "PostgreSQL" in render_prompt("SCHEMA", "Q?")  # default


def test_render_prompt_includes_evidence_only_when_given():
    with_ev = render_prompt("S", "Q?", dialect="SQLite", evidence="rate = amt / qty")
    without = render_prompt("S", "Q?", dialect="SQLite")
    assert "External knowledge" in with_ev and "rate = amt / qty" in with_ev
    assert "External knowledge" not in without


class _CaptureResponse:
    def __init__(self, text: str) -> None:
        self.content = [type("Block", (), {"text": text})()]
        self.usage = type("Usage", (), {"input_tokens": 1, "output_tokens": 1})()


class _CaptureClient:
    """A stub Anthropic client that records the prompt it was sent."""

    def __init__(self) -> None:
        self.prompt: str | None = None
        self.messages = self

    def create(self, *, model: str, max_tokens: int, messages: list[dict[str, Any]]):
        self.prompt = messages[0]["content"]
        return _CaptureResponse("SELECT 1;")


def test_generate_threads_dialect_and_evidence_into_the_prompt():
    client = _CaptureClient()
    state = RunState(question="how many?", db_id="toxicology")
    generate(
        state,
        schema="CREATE TABLE t (id INT);",
        dialect="SQLite",
        evidence="id is the key",
        client=client,
    )
    assert client.prompt is not None
    assert "SQLite" in client.prompt
    assert "id is the key" in client.prompt


# --- RESULTS.md row + append (offline) -------------------------------------


def _report(correct: int, total: int) -> BatchReport:
    results = [
        CaseResult(
            case_id=str(i),
            db_id="toxicology",
            terminal_state=(
                TerminalState.SUCCESS if i < correct else TerminalState.WRONG_ANSWER
            ),
            correct=i < correct,
        )
        for i in range(total)
    ]
    return BatchReport(tuple(results))


def test_results_row_carries_full_config():
    row = eval_bird.results_row(
        _report(9, 20),
        model="claude-sonnet-4-6",
        prompt_version=PROMPT_VERSION,
        commit="abc1234",
    )
    assert "pass@1" in row
    assert "0.450 (9/20)" in row
    assert "claude-sonnet-4-6" in row
    assert PROMPT_VERSION in row
    assert "abc1234" in row
    assert eval_bird.slice_id() in row  # reads the committed slice file


def test_append_results_adds_row_and_retires_placeholder(tmp_path: Path):
    results = tmp_path / "RESULTS.md"
    results.write_text(
        "# RESULTS\n\n_No numbers yet — first land in Step 3._\n\n## Log\n\n"
        "| Date | Step | Metric | Number |\n| - | - | - | - |\n"
        "| _—_ | _—_ | _—_ | _—_ |\n"
    )
    eval_bird.append_results("| 2026-06-11 | 3 | pass@1 | 0.500 |", results)
    text = results.read_text()
    assert "| _—_" not in text  # placeholder retired
    assert "No numbers yet" not in text
    assert text.rstrip().endswith("| 2026-06-11 | 3 | pass@1 | 0.500 |")


# --- real-data case building (skips without the BIRD download) --------------

_HAS_BIRD = (bird_data_dir() / "dev.json").exists()


@pytest.mark.skipif(not _HAS_BIRD, reason="BIRD data not downloaded")
def test_build_bird_cases_materializes_gold_for_the_whole_slice():
    cases, evidence = eval_bird.build_bird_cases()
    assert len(cases) == 50
    assert len(evidence) == 50
    for case in cases:
        assert set(case.gold_result) == {"columns", "rows"}
        assert case.id in evidence
