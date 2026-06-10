"""Terminal-state classification + the Step-1 gold-match proof (issue 5).

CI-safe: no network, no Postgres. The classifier and the exact-match gold check
are pure functions over a ``RunState``, so they're exercised with hand-built
states. The live end-to-end run (real model + seeded db) is the AFK proof in
``eval/prove_step1.py``; this file guards the deterministic pieces it leans on.
"""

from __future__ import annotations

from decimal import Decimal

from eval.harness import classify_terminal_state
from eval.prove_step1 import gold_matches
from nl2sql.pipeline.state import RunState, TerminalState


def _clean_state(columns, rows):
    state = RunState(question="q", db_id="payments")
    state.candidate_sql = "SELECT 1"
    state.result_columns = columns
    state.result_rows = rows
    return state


# --- terminal-state classifier (the two Step-1 reachable states) ------------


def test_clean_run_buckets_success():
    assert classify_terminal_state(_clean_state(["n"], [(3,)])) is TerminalState.SUCCESS


def test_execution_error_buckets_execution_error_final():
    state = RunState(question="q", db_id="payments")
    state.error = 'relation "nope" does not exist'
    assert classify_terminal_state(state) is TerminalState.EXECUTION_ERROR_FINAL


# --- Step-1 gold match (value-level rows, with driver-type normalization) ----


def test_gold_matches_on_matching_row_values():
    state = _clean_state(["n"], [(3,)])
    gold = {"gold_result": {"columns": ["n"], "rows": [[3]]}}
    assert gold_matches(state, gold) is True


def test_gold_matches_ignores_column_aliases():
    # A correct value under a different alias is still correct — the live model
    # aliased COUNT(id) AS us_user_count where gold labels it n (domain rule 1).
    state = _clean_state(["us_user_count"], [(3,)])
    gold = {"gold_result": {"columns": ["n"], "rows": [[3]]}}
    assert gold_matches(state, gold) is True


def test_gold_matches_normalizes_postgres_decimal_to_int():
    # Postgres returns SUM() as Decimal; gold stores plain int cents.
    state = _clean_state(["total_cents"], [(Decimal("5798"),)])
    gold = {"gold_result": {"columns": ["total_cents"], "rows": [[5798]]}}
    assert gold_matches(state, gold) is True


def test_gold_matches_rejects_wrong_values():
    state = _clean_state(["n"], [(2,)])
    gold = {"gold_result": {"columns": ["n"], "rows": [[3]]}}
    assert gold_matches(state, gold) is False
