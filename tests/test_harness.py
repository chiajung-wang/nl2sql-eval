"""Offline proof of the batch harness + metrics (Step 3, Issue 1).

No database, no network: the per-question runner is injected as a stub returning
canned ``RunState``s, so the harness's scoring, terminal-state classification, and
pass@1 aggregation are exercised deterministically. The live payments run
(``eval.eval_payments``) is the AFK proof against trusted ground; these tests
guard the logic underneath it.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from eval.compare import Verdict, compare
from eval.harness import (
    Case,
    batch_session_id,
    classify_terminal_state,
    run_batch,
    run_twin,
    score_run,
)
from eval.metrics import BatchReport, CaseResult
from nl2sql import obs
from nl2sql.pipeline.state import RunState, TerminalState


def _state(
    *,
    columns: list[str] | None = None,
    rows: list[tuple[Any, ...]] | None = None,
    error: str | None = None,
    sql: str | None = "SELECT 1",
) -> RunState:
    s = RunState(question="q", db_id="payments")
    s.candidate_sql = sql
    s.result_columns = columns
    s.result_rows = rows
    s.error = error
    return s


def _case(
    cid: str,
    gold_rows: list[list[Any]],
    *,
    gold_sql: str = "SELECT n FROM t",
    difficulty: str | None = None,
) -> Case:
    return Case(
        id=cid,
        question="q",
        db_id="payments",
        gold_sql=gold_sql,
        gold_result={"columns": ["n"], "rows": gold_rows},
        difficulty=difficulty,
    )


# --- the classifier --------------------------------------------------------


def test_error_run_buckets_execution_error_final():
    # Single-shot failure (attempts==0/1, no retry budget) → EXECUTION_ERROR_FINAL.
    assert (
        classify_terminal_state(_state(error="boom"))
        is TerminalState.EXECUTION_ERROR_FINAL
    )


def test_budget_exhausted_error_buckets_retry_exhausted():
    # The Step-5 loop returns an errored run only after spending its budget, so a
    # multi-attempt error is RETRY_EXHAUSTED, not EXECUTION_ERROR_FINAL.
    state = _state(error="still broken")
    state.attempts = 3
    assert classify_terminal_state(state) is TerminalState.RETRY_EXHAUSTED


def test_correct_run_buckets_success():
    ok = compare(
        {"columns": ["n"], "rows": [[1]]}, {"columns": ["n"], "rows": [[1]]}, ""
    )
    assert classify_terminal_state(_state(), ok) is TerminalState.SUCCESS


def test_clean_but_wrong_run_buckets_wrong_answer():
    wrong = compare(
        {"columns": ["n"], "rows": [[1]]}, {"columns": ["n"], "rows": [[2]]}, ""
    )
    assert classify_terminal_state(_state(), wrong) is TerminalState.WRONG_ANSWER


def test_no_comparison_is_backward_compatible_success():
    # The Step-1 proof calls the classifier with no comparison; it must still
    # bucket a clean run as SUCCESS (never WRONG_ANSWER) — back-compat.
    assert classify_terminal_state(_state()) is TerminalState.SUCCESS


# --- score_run: builds the candidate from the RunState ---------------------


def test_score_run_scores_raw_result_rows():
    state = _state(columns=["n"], rows=[(3,)])
    comparison, terminal = score_run(state, _case("c", [[3]]))
    assert comparison is not None and comparison.verdict is Verdict.CORRECT
    assert terminal is TerminalState.SUCCESS


def test_score_run_does_not_score_an_errored_run():
    comparison, terminal = score_run(_state(error="boom"), _case("c", [[3]]))
    assert comparison is None
    assert terminal is TerminalState.EXECUTION_ERROR_FINAL


# --- run_batch + aggregation -----------------------------------------------


def test_run_batch_aggregates_pass_at_1_and_terminal_mix():
    cases = [
        _case("ok", [[1]], difficulty="simple"),
        _case("wrong", [[1]], difficulty="simple"),
        _case("err", [[1]], difficulty="hard"),
    ]
    states = {
        "ok": _state(columns=["n"], rows=[(1,)]),
        "wrong": _state(columns=["n"], rows=[(2,)]),
        "err": _state(error="syntax error"),
    }
    report = run_batch(cases, lambda c: states[c.id])

    assert report.total == 3
    assert report.n_correct == 1
    assert report.pass_at_1 == 1 / 3
    counts = report.terminal_counts()
    assert counts[TerminalState.SUCCESS] == 1
    assert counts[TerminalState.WRONG_ANSWER] == 1
    assert counts[TerminalState.EXECUTION_ERROR_FINAL] == 1
    assert report.pass_at_1_by("difficulty") == {"simple": 0.5, "hard": 0.0}


def test_run_batch_routes_through_the_order_aware_comparator():
    # The harness must actually use the Step-2 comparator, not a string/exact
    # check: an unordered gold passes reordered rows; an ORDER BY gold does not.
    unordered = _case("u", [["a"], ["b"]], gold_sql="SELECT name FROM t")
    ordered = _case("o", [["a"], ["b"]], gold_sql="SELECT name FROM t ORDER BY name")
    reordered = _state(columns=["name"], rows=[("b",), ("a",)])
    report = run_batch([unordered, ordered], lambda c: reordered)

    by_id = {r.case_id: r for r in report.results}
    assert by_id["u"].terminal_state is TerminalState.SUCCESS
    assert by_id["o"].terminal_state is TerminalState.WRONG_ANSWER


def test_empty_batch_pass_at_1_is_zero_not_error():
    assert BatchReport(()).pass_at_1 == 0.0


def test_case_result_note_never_carries_rows():
    # The note is the comparator's reason or the error text — explainability
    # without leaking result values into a report/log (CLAUDE.md §5.3).
    report = run_batch(
        [_case("ok", [[1]])], lambda c: _state(columns=["n"], rows=[(1,)])
    )
    note = report.results[0].note
    assert note == "result sets match"
    assert isinstance(report.results[0], CaseResult)


# --- session grouping (Step 8 follow-up, #96) ------------------------------


def test_batch_session_id_is_stable_and_descriptive():
    today = datetime.now(UTC).date().isoformat()
    sid = batch_session_id("bird-naive", model="anthropic/claude", prompt_version="v3")
    assert sid == f"bird-naive:anthropic/claude:v3:{today}"
    # prompt_version is optional — it drops out of the id when absent.
    assert batch_session_id("payments", model="m") == f"payments:m:{today}"


@contextmanager
def _capture_sessions(monkeypatch, sink: list):
    """Record the session_id each run_batch wraps its loop in, without Langfuse."""

    @contextmanager
    def fake_trace_attributes(**kwargs):
        sink.append(kwargs.get("session_id"))
        yield

    monkeypatch.setattr(obs, "trace_attributes", fake_trace_attributes)
    yield


def test_run_batch_groups_its_loop_under_the_session(monkeypatch):
    seen: list = []
    with _capture_sessions(monkeypatch, seen):
        report = run_batch(
            [_case("ok", [[1]])],
            lambda c: _state(columns=["n"], rows=[(1,)]),
            session_id="bird-naive:m:v:2026-06-18",
        )
    # The session wraps the batch, and the cases still ran inside it.
    assert seen == ["bird-naive:m:v:2026-06-18"]
    assert report.results[0].terminal_state is TerminalState.SUCCESS


def test_run_batch_default_session_is_none(monkeypatch):
    seen: list = []
    with _capture_sessions(monkeypatch, seen):
        run_batch([_case("ok", [[1]])], lambda c: _state(columns=["n"], rows=[(1,)]))
    # No session_id → trace_attributes is entered with None (a pure no-op).
    assert seen == [None]


def test_run_twin_uses_sibling_pass1_and_passk_sessions(monkeypatch):
    seen: list = []
    state = _state(columns=["n"], rows=[(1,)])
    with _capture_sessions(monkeypatch, seen):
        run_twin(
            [_case("ok", [[1]])],
            lambda budget: lambda c: state,
            k=3,
            model="m",
            session_id="bird-twin:m:v:2026-06-18",
        )
    assert seen == [
        "bird-twin:m:v:2026-06-18:pass1",
        "bird-twin:m:v:2026-06-18:pass3",
    ]
