"""Large-schema self-correction twin — offline coverage of row/prose formatting.

No API, no BIRD download: the live run is the AFK deliverable. These tests pin the
deterministic pieces — the RESULTS.md row shape, the eligible-execution-error
count, and the two prose branches (loop fired vs never fired) — so a committed
number lands with full config and an honest decomposition.
"""

from __future__ import annotations

from eval import eval_bird_selfcorrect as sc
from eval.metrics import BatchReport, CaseResult, TwinReport
from nl2sql.pipeline.state import TerminalState

MODEL = "anthropic/claude-sonnet-4-6"


def _case(case_id: str, state: TerminalState, *, correct: bool, attempts: int = 1):
    return CaseResult(
        case_id=case_id,
        db_id="bird",
        terminal_state=state,
        correct=correct,
        attempts=attempts,
        input_tokens=100,
        output_tokens=50,
        latency_ms=10.0,
    )


def _twin_with_recovery() -> TwinReport:
    # pass@1: one ok, one execution error (eligible), one wrong-answer (semantic).
    pass1 = BatchReport(
        (
            _case("a", TerminalState.SUCCESS, correct=True),
            _case("b", TerminalState.EXECUTION_ERROR_FINAL, correct=False),
            _case("c", TerminalState.WRONG_ANSWER, correct=False),
        )
    )
    # pass@k: the execution error recovered on attempt 2; the wrong-answer didn't.
    passk = BatchReport(
        (
            _case("a", TerminalState.SUCCESS, correct=True),
            _case("b", TerminalState.SUCCESS, correct=True, attempts=2),
            _case("c", TerminalState.WRONG_ANSWER, correct=False),
        )
    )
    return TwinReport(pass1=pass1, passk=passk, model=MODEL)


def _twin_no_fire() -> TwinReport:
    # Every failure is a clean wrong-answer — the loop has nothing to feed back.
    pass1 = BatchReport(
        (
            _case("a", TerminalState.SUCCESS, correct=True),
            _case("b", TerminalState.WRONG_ANSWER, correct=False),
        )
    )
    return TwinReport(pass1=pass1, passk=pass1, model=MODEL)


def test_eligible_errors_counts_only_execution_failures():
    assert sc._eligible_errors(_twin_with_recovery()) == 1
    assert sc._eligible_errors(_twin_no_fire()) == 0


def test_results_row_carries_config_gap_and_eligible_count():
    row = sc.results_row(_twin_with_recovery(), k=3, model=MODEL, commit="abc1234")
    assert row.startswith("| ") and "| 5 |" in row
    assert "self-correction on large schemas" in row
    assert "pass@1→pass@3" in row
    assert "step6-large-schema-retrieval-lift" in row
    assert "exec-err eligible" in row
    assert "abc1234" in row and MODEL in row


def test_prose_reports_recovery_with_cost_when_loop_fires():
    prose = sc.results_prose(_twin_with_recovery(), k=3, model=MODEL)
    assert "recovers" in prose
    # 1 eligible execution error, recovered → the loop fired (added attempts > 0).
    assert "extra generate→execute cycles" in prose
    assert "never\nwithout" in prose or "never without" in prose.replace("\n", " ")


def test_prose_says_never_fired_when_no_execution_errors():
    prose = sc.results_prose(_twin_no_fire(), k=3, model=MODEL)
    assert "never fired" in prose
    assert "semantic" in prose
