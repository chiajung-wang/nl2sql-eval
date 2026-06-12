"""Step-5 DoD twin runner — offline coverage of formatting + RESULTS.md insert.

No API, no BIRD download: the live twin run is the AFK deliverable. These tests
pin the deterministic pieces — the RESULTS.md row/prose shape and the
table-insert-then-prose-append logic — so a committed number lands in the right
place with full config.
"""

from __future__ import annotations

from pathlib import Path

from eval import eval_bird_twin
from eval.metrics import BatchReport, CaseResult, TwinReport
from nl2sql.pipeline.state import TerminalState

MODEL = "claude-sonnet-4-6"


def _result(
    case_id: str, *, correct: bool, attempts: int, inp: int, out: int, ms: float
):
    return CaseResult(
        case_id=case_id,
        db_id="bird",
        terminal_state=TerminalState.SUCCESS if correct else TerminalState.WRONG_ANSWER,
        correct=correct,
        attempts=attempts,
        input_tokens=inp,
        output_tokens=out,
        latency_ms=ms,
    )


def _twin() -> TwinReport:
    pass1 = BatchReport(
        (
            _result("a", correct=True, attempts=1, inp=100, out=50, ms=10.0),
            _result("b", correct=False, attempts=1, inp=100, out=50, ms=10.0),
        )
    )
    passk = BatchReport(
        (
            _result("a", correct=True, attempts=1, inp=100, out=50, ms=10.0),
            _result("b", correct=True, attempts=2, inp=200, out=100, ms=22.0),
        )
    )
    return TwinReport(pass1=pass1, passk=passk, model=MODEL)


def test_results_row_carries_full_config_and_the_gap():
    row = eval_bird_twin.results_row(
        _twin(), k=3, model=MODEL, prompt_version="generate/v3", commit="abc1234"
    )
    assert row.startswith("| ")
    assert "| 5 |" in row  # step
    assert "pass@1→pass@3" in row
    assert "0.500" in row and "1.000" in row  # pass@1 and pass@k
    assert "gap +0.500" in row
    assert MODEL in row
    assert "generate/v3" in row
    assert "abc1234" in row


def test_results_prose_states_the_recovery_finding_in_plain_terms():
    # _twin()'s pass@1 failure (case b) is a WRONG_ANSWER that recovers under
    # pass@k via 2 attempts — so the loop did fire (added_attempts > 0).
    prose = eval_bird_twin.results_prose(_twin(), k=3, model=MODEL)
    assert prose.startswith("**Step 5")
    assert "recovers" in prose
    assert "1/1" in prose  # one failure, recovered
    assert "100%" in prose  # recovery rate
    assert "added" in prose and "ms" in prose
    assert "eval.eval_bird_twin" in prose


def test_results_prose_explains_a_zero_gap_when_no_correction_fires():
    # pass@1 and pass@k identical, every failure a wrong-answer, no retries: the
    # prose must say the loop never fired and the gap is necessarily zero.
    wrong = _batch_with(
        [
            _result("a", correct=True, attempts=1, inp=10, out=5, ms=1.0),
            _result("b", correct=False, attempts=1, inp=10, out=5, ms=1.0),
        ]
    )
    twin = TwinReport(pass1=wrong, passk=wrong, model=MODEL)
    prose = eval_bird_twin.results_prose(twin, k=3, model=MODEL)
    assert "never fired" in prose
    assert "+0.000" in prose
    assert "semantic, not syntactic" in prose
    assert "1" in prose  # the single wrong-answer failure is counted


def _batch_with(rows: tuple[CaseResult, ...] | list[CaseResult]) -> BatchReport:
    return BatchReport(tuple(rows))


def test_append_results_inserts_row_in_table_and_prose_at_eof(tmp_path: Path):
    results = tmp_path / "RESULTS.md"
    results.write_text(
        "# RESULTS\n\n## Log\n\n"
        "| Date | Step | Metric | Number |\n"
        "| ---- | ---- | ------ | ------ |\n"
        "| 2026-06-11 | 3 | pass@1 | 0.420 |\n"
        "| 2026-06-12 | 4 | catch rate | 1.000 |\n\n"
        "**Step 4 — guardrail catch rate.** Prior prose paragraph.\n"
    )

    step5 = "| 2026-06-12 | 5 | pass@1→pass@3 | 0.500 → 1.000 |"
    eval_bird_twin.append_results(
        step5,
        "**Step 5 — the finding.** New prose.",
        results_path=results,
    )

    out = results.read_text()
    lines = out.splitlines()
    table_rows = [i for i, ln in enumerate(lines) if ln.startswith("|")]
    step5_row = next(i for i, ln in enumerate(lines) if "| 5 |" in ln)
    step4_prose = next(i for i, ln in enumerate(lines) if ln.startswith("**Step 4"))
    step5_prose = next(i for i, ln in enumerate(lines) if ln.startswith("**Step 5"))

    # The Step-5 row sits inside the contiguous table block (after the last row).
    assert step5_row == max(table_rows)
    # Prose stays after the table; the new finding is appended at the very end.
    assert step5_row < step4_prose < step5_prose
    assert step5_prose == len(lines) - 1


def test_make_factory_binds_the_budget_into_callables():
    factory = eval_bird_twin.make_factory({"q": "hint"})
    assert callable(factory(1))
    assert callable(factory(3))
