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

import json
from pathlib import Path

import pytest

from eval.harness import Case, classify_terminal_state, run_batch, score_run
from eval.redteam import DEFAULT_CASE_DIALECT, evaluate, load_cases
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.guard import GuardDecision, guard, guard_sql
from nl2sql.pipeline.state import RunState, TerminalState

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BIRD_DIR = _REPO_ROOT / "eval" / "datasets" / "bird"


def _load_bird_slice_gold_sql() -> list[str]:
    """The gold SQL of every question in the frozen Step-3 BIRD slice."""
    ids = set(json.loads((_BIRD_DIR / "slice_step3.json").read_text())["question_ids"])
    dev = json.loads((_BIRD_DIR / "data" / "dev.json").read_text())
    return [q["SQL"] for q in dev if q["question_id"] in ids]


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
    result = guard_sql(case["sql"], dialect=case.get("dialect", DEFAULT_CASE_DIALECT))
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


def test_replace_into_command_write_is_rejected():
    # SQLite REPLACE INTO parses as a generic Command (not a typed Insert); a
    # node-type blocklist alone would wave this data write through.
    result = guard_sql("REPLACE INTO users VALUES (1)", dialect="sqlite")
    assert result.rejected and result.rule == "read_only"


def test_cte_wrapped_write_is_rejected():
    # A DELETE smuggled in a CTE has a top-level SELECT root; the rule must walk
    # the subtree, not just check the root statement type.
    result = guard_sql(
        "WITH g AS (DELETE FROM t RETURNING id) SELECT id FROM g", dialect="postgres"
    )
    assert result.rejected and result.rule == "read_only"


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


# --- dangerous-op rule -----------------------------------------------------


def test_attach_database_is_rejected_dangerous_op():
    result = guard_sql("ATTACH DATABASE 'evil.db' AS evil", dialect="sqlite")
    assert result.rejected and result.rule == "dangerous_op"


def test_detach_database_is_rejected_dangerous_op():
    result = guard_sql("DETACH DATABASE evil", dialect="sqlite")
    assert result.rejected and result.rule == "dangerous_op"


def test_all_pragma_is_rejected_even_introspection():
    # Read- vs write-PRAGMA can't be told apart reliably on the AST and no PRAGMA
    # is a valid answer, so the gate default-denies all of them.
    assert (
        guard_sql("PRAGMA writable_schema=ON", dialect="sqlite").rule == "dangerous_op"
    )
    assert (
        guard_sql("PRAGMA table_info(users)", dialect="sqlite").rule == "dangerous_op"
    )


def test_stacked_statements_are_rejected_dangerous_op():
    # Both statements are reads, so read-only passes; a question maps to one
    # query, so the stacked shape is the dangerous-op rule's catch.
    result = guard_sql("SELECT 1; SELECT 2", dialect="sqlite")
    assert result.rejected and result.rule == "dangerous_op"


def test_unmodeled_command_is_rejected_dangerous_op():
    result = guard_sql("VACUUM", dialect="sqlite")
    assert result.rejected and result.rule == "dangerous_op"


def test_read_only_takes_precedence_over_dangerous_op():
    # A stacked candidate whose second statement writes is caught by read-only
    # first (fail-fast, rules in order) — precedence is deterministic.
    result = guard_sql("SELECT name FROM users; DROP TABLE users", dialect="sqlite")
    assert result.rejected and result.rule == "read_only"


def test_trailing_semicolon_comment_is_not_a_stacked_query():
    # `SELECT 1; -- note` parses into [Select, Semicolon]; the empty trailing
    # node must be dropped so a single query is not misread as stacked.
    assert guard_sql("SELECT 1; -- trailing note", dialect="sqlite").allowed
    assert guard_sql("SELECT 1;", dialect="sqlite").allowed


def test_dangerous_op_does_not_misfire_on_a_complex_read():
    sql = (
        "SELECT u.name, COUNT(t.id) FROM users u "
        "JOIN transactions t ON t.user_id = u.id GROUP BY u.name"
    )
    assert guard_sql(sql, dialect="sqlite").allowed


# --- cost/complexity heuristic ---------------------------------------------


def test_comma_cartesian_product_is_rejected_cost():
    result = guard_sql("SELECT a.id FROM users a, transactions b", dialect="sqlite")
    assert result.rejected and result.rule == "cost"


def test_cross_join_is_rejected_cost():
    result = guard_sql("SELECT * FROM users CROSS JOIN merchants", dialect="sqlite")
    assert result.rejected and result.rule == "cost"


def test_old_style_join_with_where_is_not_cartesian():
    # FROM a, b WHERE a.id = b.id is a legitimate inner join — the connecting
    # WHERE means it is not an unconstrained cross product.
    sql = "SELECT a.name FROM users a, transactions b WHERE a.id = b.user_id"
    assert guard_sql(sql, dialect="sqlite").allowed


def test_join_explosion_is_rejected_cost():
    sql = (
        "SELECT u.id FROM users u "
        "JOIN a ON a.id = u.id JOIN b ON b.id = a.id JOIN c ON c.id = b.id "
        "JOIN d ON d.id = c.id JOIN e ON e.id = d.id"
    )
    result = guard_sql(sql, dialect="sqlite")
    assert result.rejected and result.rule == "cost"


def test_unbounded_star_scan_is_rejected_cost():
    result = guard_sql("SELECT * FROM transactions", dialect="sqlite")
    assert result.rejected and result.rule == "cost"


def test_star_with_where_or_limit_is_allowed():
    assert guard_sql("SELECT * FROM t WHERE amount > 1", dialect="sqlite").allowed
    assert guard_sql("SELECT * FROM t LIMIT 10", dialect="sqlite").allowed


def test_count_star_is_not_an_unbounded_scan():
    # COUNT(*)'s star is nested in the function, not a top-level projection.
    assert guard_sql("SELECT COUNT(*) FROM t", dialect="sqlite").allowed


def test_cost_budget_clears_every_bird_slice_gold_query():
    # The thresholds are calibrated against the frozen slice: if any legitimate
    # gold query tripped the cost gate, the live BIRD pass@1 would silently drop.
    # This pins the calibration so a future threshold change can't regress it.
    gold = _load_bird_slice_gold_sql()
    assert len(gold) == 50, f"expected the frozen 50-question slice, got {len(gold)}"
    rejected = [sql for sql in gold if guard_sql(sql, dialect="sqlite").rule == "cost"]
    assert not rejected, f"cost gate rejected legitimate gold SQL: {rejected}"


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
