"""Result-set majority voting + candidate diversity (Step 12, #142) — offline.

The novel core — the comparator repurposed from gold-scoring to candidate
selection — is fully offline and proven here on recorded result-sets: the majority
vote, its deterministic earliest-index tiebreak, the agreement distribution, and the
deterministic schema-field-order diversity lever. No network, no key; the live twin
(pass@1 vs pass@k-majority on strong/weak generators) is deferred.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from eval.candidate_diversity import shuffle_field_order
from eval.voting import (
    Candidate,
    agreement_distribution,
    candidate_from_state,
    majority_vote,
    run_voted,
    select_by_vote,
)
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import build_schema_index


def _result(rows, columns=("x",)):
    return {"columns": list(columns), "rows": list(rows)}


def _cand(rows, **kw):
    return Candidate(_result(rows), **kw)


# --- majority_vote: the comparator as a selector -----------------------------


def test_unanimous_candidates_are_one_group():
    outcome = majority_vote([_cand([(1,)]), _cand([(1,)]), _cand([(1,)])])
    assert outcome.n_groups == 1
    assert outcome.agreement == 3
    assert outcome.selected_index == 0
    assert outcome.tie is False


def test_two_thirds_majority_selects_earliest_in_winning_class():
    # Candidates 0 and 2 agree; 1 differs. The winning class is {0, 2} → pick 0.
    outcome = majority_vote([_cand([(1,)]), _cand([(2,)]), _cand([(1,)])])
    assert outcome.agreement == 2
    assert outcome.n_groups == 2
    assert outcome.selected_index == 0
    assert outcome.tie is False


def test_no_majority_breaks_tie_by_earliest_index():
    # Three distinct result-sets — every class size 1; the earliest wins (index 0).
    outcome = majority_vote([_cand([(3,)]), _cand([(1,)]), _cand([(2,)])])
    assert outcome.n_groups == 3
    assert outcome.selected_index == 0
    assert outcome.tie is True  # a tiebreak decided it


def test_tie_between_two_pairs_picks_earliest_pair():
    # {0,2} and {1,3} both size 2 — the class with the earliest index (0) wins.
    outcome = majority_vote(
        [_cand([(1,)]), _cand([(9,)]), _cand([(1,)]), _cand([(9,)])]
    )
    assert outcome.agreement == 2
    assert outcome.selected_index == 0
    assert outcome.tie is True


def test_errored_candidates_are_excluded():
    outcome = majority_vote([_cand([], errored=True), _cand([(9,)]), _cand([(9,)])])
    assert outcome.selected_index == 1  # the errored candidate can't be chosen
    assert outcome.agreement == 2


def test_all_errored_returns_first_never_loses_the_run():
    outcome = majority_vote([_cand([], errored=True), _cand([], errored=True)])
    assert outcome.selected_index == 0
    assert outcome.agreement == 0
    assert outcome.n_groups == 0


def test_single_candidate_is_selected():
    outcome = majority_vote([_cand([(1,)])])
    assert outcome.selected_index == 0 and outcome.agreement == 1


def test_empty_candidate_list_raises():
    with pytest.raises(ValueError, match="at least one candidate"):
        majority_vote([])


# --- voting reuses the comparator's equivalence (not string match) -----------


def test_order_insensitive_results_vote_together():
    # Same rows, different order → the comparator's set rules make them equivalent.
    outcome = majority_vote([_result_cand([(1,), (2,)]), _result_cand([(2,), (1,)])])
    assert outcome.n_groups == 1  # not two distinct sets


def _result_cand(rows):
    return Candidate({"columns": ["x"], "rows": rows})


def test_float_tolerance_results_vote_together():
    # The comparator's float-tolerance rule is reused — near-equal floats agree.
    a = Candidate({"columns": ["v"], "rows": [(1.000000001,)]})
    b = Candidate({"columns": ["v"], "rows": [(1.0,)]})
    assert majority_vote([a, b]).n_groups == 1


# --- from RunState / select_by_vote ------------------------------------------


def _state(rows, *, sql="SELECT 1", error=None):
    st = RunState(question="q", db_id="d")
    st.candidate_sql = sql
    st.result_columns = ["x"]
    st.result_rows = rows
    st.error = error
    return st


def test_candidate_from_state_uses_raw_result():
    cand = candidate_from_state(_state([(1,)]))
    assert cand.result == {"columns": ["x"], "rows": [(1,)]}
    assert cand.errored is False


def test_candidate_from_state_marks_error_and_no_rows():
    assert candidate_from_state(_state(None, error="boom")).errored is True
    assert candidate_from_state(_state(None)).errored is True


def test_select_by_vote_returns_the_majority_state():
    states = [_state([(1,)]), _state([(2,)]), _state([(1,)])]
    selected, outcome = select_by_vote(states)
    assert selected is states[0]
    assert outcome.agreement == 2


# --- run_voted orchestration -------------------------------------------------


def test_run_voted_generates_k_and_selects_majority():
    def run_one(i: int) -> RunState:
        return _state([(1,)] if i in (0, 2) else [(2,)])

    selected, outcome, candidates = run_voted(run_one, 3)
    assert len(candidates) == 3
    assert selected.result_rows == [(1,)]
    assert outcome.agreement == 2


def test_run_voted_rejects_bad_k():
    with pytest.raises(ValueError, match="k >= 1"):
        run_voted(lambda i: _state([(1,)]), 0)


# --- agreement distribution --------------------------------------------------


def test_agreement_distribution_buckets():
    outcomes = [
        majority_vote([_cand([(1,)]), _cand([(1,)]), _cand([(1,)])]),  # unanimous
        majority_vote([_cand([(1,)]), _cand([(2,)]), _cand([(1,)])]),  # majority
        majority_vote([_cand([(3,)]), _cand([(1,)]), _cand([(2,)])]),  # no_majority
    ]
    assert agreement_distribution(outcomes) == {
        "unanimous": 1,
        "majority": 1,
        "no_majority": 1,
    }


def test_agreement_distribution_denominator_excludes_errored():
    # 2 votable candidates agree, 1 errored: 2 of 2 votable is unanimous — the errored
    # candidate must not push it toward no_majority (denominator is votable, not all).
    outcome = majority_vote([_cand([(1,)]), _cand([(1,)]), _cand([], errored=True)])
    assert outcome.n_votable == 2 and outcome.n_groups == 1
    assert agreement_distribution([outcome]) == {
        "unanimous": 1,
        "majority": 0,
        "no_majority": 0,
    }


# --- candidate diversity: schema-field-order randomization -------------------


@pytest.fixture
def index():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE t (a INTEGER, b INTEGER, c INTEGER, d INTEGER, e INTEGER)"
            )
        )
    return build_schema_index(engine)


def test_shuffle_is_deterministic_in_seed(index):
    order1 = [c.name for c in shuffle_field_order(index, 7).tables[0].columns]
    order2 = [c.name for c in shuffle_field_order(index, 7).tables[0].columns]
    assert order1 == order2


def test_shuffle_is_a_permutation_that_changes_order(index):
    base = [c.name for c in index.tables[0].columns]
    shuffled = [c.name for c in shuffle_field_order(index, 3).tables[0].columns]
    assert sorted(shuffled) == sorted(base)  # same columns
    assert shuffled != base  # different order


def test_shuffle_seed_zero_is_identity(index):
    assert shuffle_field_order(index, 0) is index


def test_different_seeds_give_different_orders(index):
    a = [c.name for c in shuffle_field_order(index, 1).tables[0].columns]
    b = [c.name for c in shuffle_field_order(index, 2).tables[0].columns]
    assert a != b


def test_shuffle_preserves_table_and_metadata():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE child (id INTEGER, parent_id INTEGER, "
                "FOREIGN KEY (parent_id) REFERENCES parent(id))"
            )
        )
    index = build_schema_index(engine)
    shuffled = shuffle_field_order(index, 4)
    # Same tables in the same order; FKs preserved (only column order changes).
    assert [t.name for t in shuffled.tables] == [t.name for t in index.tables]
    child = {t.name: t for t in shuffled.tables}["child"]
    assert child.foreign_keys == (("parent_id", "parent"),)
