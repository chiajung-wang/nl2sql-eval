"""Twin-metric aggregation: pass@1 vs pass@k + attempts/cost/latency (Step 5, #43).

Offline and deterministic — the cost table is fixed, attempts/tokens/latency are
fed in as known values via stub runners, so the gap, recovery rate, and added
cost/latency are exact. The live BIRD twin run is issue #44; these tests guard the
machinery underneath it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from eval.cost import PRICES, cost_usd
from eval.harness import Case, derive_pass1_report, run_batch, run_twin
from eval.metrics import BatchReport, CaseResult, TwinReport, twin_summary_lines
from nl2sql.pipeline.generate import DEFAULT_MODEL
from nl2sql.pipeline.state import RunState, TerminalState

MODEL = DEFAULT_MODEL  # claude-sonnet-4-6 — priced in the table


# --- cost table -------------------------------------------------------------


def test_cost_usd_prices_sonnet_input_and_output():
    # 1000 input + 500 output on sonnet-4-6 ($3 / $15 per 1M):
    # (1000*3 + 500*15) / 1e6 = 0.0105
    assert cost_usd("claude-sonnet-4-6", 1000, 500) == 0.0105


def test_cost_usd_is_none_for_an_unpriced_model():
    assert "totally-made-up-model" not in PRICES
    assert cost_usd("totally-made-up-model", 10, 10) is None


# --- BatchReport cost/latency/attempts aggregates ---------------------------


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


def test_batch_report_aggregates_attempts_tokens_latency_cost():
    report = BatchReport(
        (
            _result("a", correct=True, attempts=1, inp=100, out=50, ms=10.0),
            _result("b", correct=True, attempts=2, inp=300, out=100, ms=30.0),
        )
    )
    assert report.total_attempts == 3
    assert report.mean_attempts == 1.5
    assert report.total_input_tokens == 400
    assert report.total_output_tokens == 150
    assert report.total_latency_ms == 40.0
    assert report.mean_latency_ms == 20.0
    # (400*3 + 150*15) / 1e6 = (1200 + 2250)/1e6 = 0.00345
    assert report.cost_usd(MODEL) == 0.00345
    assert report.accuracy == 1.0
    assert report.pass_at_1 == 1.0  # alias still resolves


# --- TwinReport: the headline gap and its price -----------------------------


def _batch(rows: list[tuple[str, bool, int, int, int, float]]) -> BatchReport:
    return BatchReport(
        tuple(
            _result(cid, correct=c, attempts=a, inp=i, out=o, ms=m)
            for cid, c, a, i, o, m in rows
        )
    )


def test_twin_report_gap_recovery_and_added_cost():
    # pass@1: q1 right, q2 wrong, q3 wrong (1/3). One attempt, 100in/50out each.
    pass1 = _batch(
        [
            ("q1", True, 1, 100, 50, 10.0),
            ("q2", False, 1, 100, 50, 10.0),
            ("q3", False, 1, 100, 50, 10.0),
        ]
    )
    # pass@k: q1 right, q2 recovers (2 attempts), q3 still wrong (3 attempts). 2/3.
    passk = _batch(
        [
            ("q1", True, 1, 100, 50, 10.0),
            ("q2", True, 2, 200, 100, 22.0),
            ("q3", False, 3, 300, 150, 33.0),
        ]
    )
    twin = TwinReport(pass1=pass1, passk=passk, model=MODEL)

    assert twin.pass_at_1 == 1 / 3
    assert twin.pass_at_k == 2 / 3
    assert abs(twin.gap - 1 / 3) < 1e-12
    # Two failed pass@1; one (q2) recovered.
    assert twin.recovery_rate == 0.5
    # Extra cycles: passk total attempts 6 vs pass1 3.
    assert twin.added_attempts == 3
    assert twin.added_latency_ms == (10 + 22 + 33) - (10 + 10 + 10)
    # added cost = passk cost − pass1 cost, both on sonnet.
    expected = passk.cost_usd(MODEL) - pass1.cost_usd(MODEL)
    assert abs(twin.added_cost_usd - expected) < 1e-12


def test_recovery_rate_zero_when_pass_at_1_already_perfect():
    perfect = _batch([("q1", True, 1, 10, 10, 1.0)])
    twin = TwinReport(pass1=perfect, passk=perfect, model=MODEL)
    assert twin.recovery_rate == 0.0
    assert twin.gap == 0.0


def test_added_cost_is_none_for_unpriced_model():
    b = _batch([("q1", True, 1, 10, 10, 1.0)])
    assert TwinReport(pass1=b, passk=b, model="no-price").added_cost_usd is None


def test_twin_summary_lines_state_the_finding_plainly():
    pass1 = _batch([("q1", True, 1, 100, 50, 10.0), ("q2", False, 1, 100, 50, 10.0)])
    passk = _batch([("q1", True, 1, 100, 50, 10.0), ("q2", True, 2, 200, 100, 20.0)])
    text = "\n".join(twin_summary_lines(TwinReport(pass1, passk, MODEL)))
    assert "pass@1: 0.500" in text
    assert "pass@k: 1.000" in text
    assert "gap" in text
    assert "recovery" in text
    assert "added cost" in text
    assert MODEL in text


# --- run_batch captures the cost off the RunState ---------------------------


def test_run_batch_captures_attempts_tokens_and_latency_from_state():
    case = Case(
        id="c",
        question="q",
        db_id="bird",
        gold_sql="SELECT n FROM t",
        gold_result={"columns": ["n"], "rows": [[3]]},
    )

    def run_one(_case: Case) -> RunState:
        s = RunState(question="q", db_id="bird")
        s.candidate_sql = "SELECT 3 AS n"
        s.result_columns = ["n"]
        s.result_rows = [(3,)]
        s.attempts = 2
        s.meta["input_tokens"] = 222
        s.meta["output_tokens"] = 14
        return s

    report = run_batch([case], run_one)
    r = report.results[0]
    assert r.correct is True
    assert r.attempts == 2
    assert r.input_tokens == 222
    assert r.output_tokens == 14
    assert r.latency_ms >= 0.0  # measured wall-clock around the run


# --- run_twin orchestration -------------------------------------------------


def test_run_twin_runs_same_cases_off_then_on():
    cases = [
        Case("q1", "q1", "bird", "SELECT n FROM t", {"columns": ["n"], "rows": [[1]]}),
        Case("q2", "q2", "bird", "SELECT n FROM t", {"columns": ["n"], "rows": [[2]]}),
    ]

    def _state(rows, *, attempts: int) -> RunState:
        s = RunState(question="q", db_id="bird")
        s.candidate_sql = "SELECT 1"
        s.result_columns = ["n"]
        s.result_rows = rows
        s.attempts = attempts
        s.meta["input_tokens"] = 100 * attempts
        s.meta["output_tokens"] = 10 * attempts
        return s

    # q1 passes either way; q2 is wrong at pass@1 (returns 99) but recovers at pass@k.
    def factory(max_attempts: int):
        def run_one(case: Case) -> RunState:
            if case.id == "q1":
                return _state([(1,)], attempts=1)
            if max_attempts == 1:
                return _state([(99,)], attempts=1)  # wrong first attempt
            return _state([(2,)], attempts=2)  # recovered under budget

        return run_one

    twin = run_twin(cases, factory, k=3, model=MODEL)

    assert isinstance(twin, TwinReport)
    assert twin.pass_at_1 == 0.5
    assert twin.pass_at_k == 1.0
    assert twin.recovery_rate == 1.0  # the one failure recovered
    assert twin.added_attempts == 1  # q2 took 2 vs 1; q1 unchanged
    assert twin.added_cost_usd is not None and twin.added_cost_usd > 0


# --- derive_pass1_report: the rigorous single-run twin ----------------------


def test_derive_pass1_report_reads_first_attempt_off_one_run():
    # One pass@k run: a clean-correct (1 attempt), a recovered run (2 attempts,
    # ended correct → attempt 1 errored), a clean-wrong single attempt, and a
    # budget-exhausted run (3 attempts, errored).
    passk = BatchReport(
        (
            CaseResult(
                "ok",
                "bird",
                TerminalState.SUCCESS,
                True,
                attempts=1,
                input_tokens=100,
                output_tokens=10,
                latency_ms=10.0,
            ),
            CaseResult(
                "rec",
                "bird",
                TerminalState.SUCCESS,
                True,
                attempts=2,
                input_tokens=200,
                output_tokens=20,
                latency_ms=20.0,
            ),
            CaseResult(
                "wrong",
                "bird",
                TerminalState.WRONG_ANSWER,
                False,
                attempts=1,
                input_tokens=100,
                output_tokens=10,
                latency_ms=10.0,
            ),
            CaseResult(
                "exh",
                "bird",
                TerminalState.RETRY_EXHAUSTED,
                False,
                attempts=3,
                input_tokens=300,
                output_tokens=30,
                latency_ms=30.0,
            ),
        )
    )
    pass1 = derive_pass1_report(passk)
    by = {r.case_id: r for r in pass1.results}

    # clean-correct on attempt 1 → still SUCCESS.
    assert by["ok"].correct and by["ok"].terminal_state is TerminalState.SUCCESS
    # recovered → attempt 1 errored → pass@1 wrong, EXECUTION_ERROR_FINAL.
    assert not by["rec"].correct
    assert by["rec"].terminal_state is TerminalState.EXECUTION_ERROR_FINAL
    # clean-wrong single attempt → unchanged.
    assert not by["wrong"].correct
    assert by["wrong"].terminal_state is TerminalState.WRONG_ANSWER
    # budget-exhausted → attempt 1 errored.
    assert by["exh"].terminal_state is TerminalState.EXECUTION_ERROR_FINAL
    # pass@1 is single-shot by definition.
    assert all(r.attempts == 1 for r in pass1.results)
    # first-attempt cost share (even split): rec 200//2=100, 20//2=10.
    assert by["rec"].input_tokens == 100 and by["rec"].output_tokens == 10

    twin = TwinReport(pass1=pass1, passk=passk, model=MODEL)
    assert twin.pass_at_1 == 1 / 4  # only "ok" correct on attempt 1
    assert twin.pass_at_k == 2 / 4  # ok + rec
    assert twin.gap == 1 / 4  # rec is what self-correction recovered
    assert twin.added_attempts == (1 + 2 + 1 + 3) - 4  # extra retry cycles
    assert twin.recovery_rate == 1 / 3  # 1 of 3 pass@1 failures recovered


# --- generate accumulates token usage across attempts on the state ----------


def test_generate_accumulates_token_usage_on_state():
    from nl2sql.pipeline.generate import generate

    class _Client:
        def __init__(self) -> None:
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **_: Any):
            return SimpleNamespace(
                content=[SimpleNamespace(text="SELECT 1")],
                usage=SimpleNamespace(input_tokens=40, output_tokens=8),
            )

    state = RunState(question="q", db_id="bird")
    generate(state, schema="CREATE TABLE t (id INT);", client=_Client())
    generate(state, schema="CREATE TABLE t (id INT);", client=_Client())  # retry

    assert state.meta["input_tokens"] == 80
    assert state.meta["output_tokens"] == 16
