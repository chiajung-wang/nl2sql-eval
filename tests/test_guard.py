"""Proof of the deterministic guardrail gate (Step 4).

Three layers, mirroring how the comparator is proven:

1. **Fixture-driven** — every ``(candidate SQL, expected verdict)`` case under
   ``fixtures/redteam_guard/`` is replayed through ``guard_sql``; adding a case
   to the fixture is exercised automatically (CLAUDE.md §8, §11).
2. **Unit** — the contract of ``guard_sql``/``GuardResult`` beyond what the
   fixture verdicts assert (boundary cases, AST-not-regex behavior).
3. **Wiring + measurement** — the gate runs between generate and execute in the
   import-shared pipeline, a rejected candidate is classified ``GUARDRAIL_REJECTED``
   and never executes, and the red-team catch rate is computed from the fixture.
"""

from __future__ import annotations

import pytest

from eval.harness import Case, classify_terminal_state, run_batch, score_run
from eval.redteam import evaluate, load_cases
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.guard import GuardDecision, guard, guard_sql
from nl2sql.pipeline.state import RunState, TerminalState

# --- 1. fixture-driven proof ----------------------------------------------

REDTEAM_CASES = load_cases()


def test_fixture_is_non_empty():
    # Guards against a glob/parse regression silently turning the proof into a
    # no-op (zero cases would otherwise vacuously "pass").
    assert REDTEAM_CASES, "no redteam_guard cases loaded — fixture missing/unparseable"


@pytest.mark.parametrize(
    "case", [pytest.param(c, id=f"{c['_file']}:{c['id']}") for c in REDTEAM_CASES]
)
def test_redteam_fixture_verdicts(case):
    result = guard_sql(case["sql"], dialect=case.get("dialect", "sqlite"))
    assert result.decision.value == case["expected_verdict"], (
        f"{case['id']}: {result.note}"
    )
    if case.get("expected_rule") is not None:
        assert result.rule == case["expected_rule"], (
            f"{case['id']}: fired '{result.rule}', expected '{case['expected_rule']}'"
        )


# --- 2. unit contract of guard_sql ----------------------------------------


def test_plain_select_is_allowed():
    assert guard_sql("SELECT 1").allowed


def test_write_is_rejected_with_read_only_rule():
    result = guard_sql("DELETE FROM users")
    assert result.rejected
    assert result.decision is GuardDecision.REJECT
    assert result.rule == "read_only"


def test_read_only_is_ast_typed_not_keyword_regex():
    # A column literally named "delete" must not trip the write/DDL check — the
    # rule keys off the statement AST type, never a substring (CLAUDE.md §4).
    assert guard_sql('SELECT "delete" FROM audit_log').allowed


def test_empty_sql_is_allowed_so_execute_owns_the_missing_sql_case():
    # No candidate is a generation gap, not a safety rejection; the gate stays
    # out of the way so execute records it as it always has.
    assert guard_sql(None).allowed
    assert guard_sql("   ").allowed


def test_unparseable_sql_is_rejected_default_deny():
    result = guard_sql("this is not sql ))(", dialect="sqlite")
    assert result.rejected
    assert result.rule == "parse_error"


def test_note_composes_rule_and_reason():
    note = guard_sql("DROP TABLE t").note
    assert note is not None and note.startswith("read_only:")


# --- 3. pipeline wiring + classification -----------------------------------


def test_guard_stage_marks_state_on_reject():
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "DROP TABLE ledger"
    guard(state, dialect="sqlite")
    assert state.guard_rejected
    assert state.guard_reason is not None


def test_guard_stage_leaves_clean_select_untouched():
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "SELECT 1"
    guard(state, dialect="sqlite")
    assert not state.guard_rejected
    assert state.guard_reason is None


class _FakeClient:
    """Stands in for the Anthropic client: returns a fixed candidate SQL."""

    def __init__(self, sql: str):
        self._sql = sql

    @property
    def messages(self):
        return self

    def create(self, **_kwargs):
        text = self._sql

        class _Resp:
            content = [type("C", (), {"text": text})()]
            usage = None

        return _Resp()


def test_rejected_candidate_never_reaches_execute():
    # An exploding engine proves execute is skipped: if the gate let a write
    # through, calling .connect() would raise instead of returning cleanly.
    class _ExplodingEngine:
        def connect(self):
            raise AssertionError("execute must not run on a guard-rejected candidate")

    state = run_pipeline(
        "drop the ledger",
        schema="-- schema --",
        engine=_ExplodingEngine(),
        dialect="sqlite",
        client=_FakeClient("DROP TABLE ledger"),
    )
    assert state.guard_rejected
    assert state.result_rows is None
    assert state.error is None


def test_guard_rejected_run_buckets_guardrail_rejected_and_is_not_scored():
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "DELETE FROM users"
    state.guard_rejected = True
    state.guard_reason = (
        "read_only: DELETE mutates data or schema; the gate is read-only"
    )

    assert classify_terminal_state(state) is TerminalState.GUARDRAIL_REJECTED

    case = Case(
        id="c",
        question="q",
        db_id="payments",
        gold_sql="SELECT 1",
        gold_result={"columns": ["n"], "rows": [[1]]},
    )
    comparison, terminal = score_run(state, case)
    assert comparison is None  # a rejected run is never scored
    assert terminal is TerminalState.GUARDRAIL_REJECTED


def test_run_batch_surfaces_guard_reason_as_note():
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "DROP TABLE t"
    state.guard_rejected = True
    state.guard_reason = "read_only: DROP mutates data or schema; the gate is read-only"
    case = Case(
        id="c",
        question="q",
        db_id="payments",
        gold_sql="SELECT 1",
        gold_result={"columns": ["n"], "rows": [[1]]},
    )
    report = run_batch([case], lambda _c: state)
    result = report.results[0]
    assert result.terminal_state is TerminalState.GUARDRAIL_REJECTED
    assert not result.correct
    assert result.note == state.guard_reason


# --- catch-rate measurement seam ------------------------------------------


def test_catch_rate_over_fixture_is_total():
    # The read-only fixture's dangerous (reject) cases must all be caught; the
    # gate matches every benign verdict too. This is the seam #35's RESULTS entry
    # reports against.
    report = evaluate(REDTEAM_CASES)
    assert report.n_dangerous > 0
    assert report.all_verdicts_match, report.mismatches()
    assert report.all_rules_match, report.mismatches()
    assert report.catch_rate == 1.0
