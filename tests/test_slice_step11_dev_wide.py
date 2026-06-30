"""The frozen Step-11 wide-dev slice — superset of dev, holdout-disjoint, stratified.

Two layers: the pure ``select_superset_slice`` logic (covered on a synthetic pool,
no BIRD download), then the committed artifact's load-bearing invariants — it is a
strict **superset** of the dev slice (continuity with the 0.420 trail), strictly
**disjoint from the held-out** slice (the generalization guard), and adds no *new*
prompt-CI overlap beyond what the dev base already had.
"""

from __future__ import annotations

import json

import pytest

from eval.datasets.bird.slice import load_slice_ids, select_superset_slice
from eval.datasets.bird.slice_ci import load_ci_slice_ids
from eval.datasets.bird.slice_step11_dev_wide import (
    SEED,
    SLICE_FILE,
    SLICE_SIZE,
    load_dev_wide_slice_ids,
)
from eval.datasets.bird.slice_step11_holdout import load_holdout_slice_ids

# --- pure select_superset_slice (synthetic pool) ----------------------------


def _pool(n_per_diff: int = 20) -> list[dict]:
    qs, qid = [], 0
    for diff in ("simple", "moderate", "challenging"):
        for _ in range(n_per_diff):
            qs.append({"question_id": qid, "db_id": "d", "difficulty": diff})
            qid += 1
    return qs


_TC = {"d": 4}  # one small-schema db


def test_superset_contains_base_and_hits_target_size():
    qs = _pool()
    base = [0, 1, 2, 45, 46]  # some simple (0-19), some challenging (40-59)
    ids = select_superset_slice(qs, _TC, base, n=30, seed=1)
    assert set(base) <= set(ids)
    assert len(ids) == 30
    assert ids == sorted(ids)


def test_superset_topup_excludes_are_honored_but_base_is_forced():
    qs = _pool()
    base = [0, 1]
    # Exclude 0 and 1 (in the base) plus 40..59 (moderate). Base stays in verbatim;
    # the top-up never draws an excluded id.
    exclude = frozenset({0, 1} | set(range(40, 60)))
    ids = select_superset_slice(qs, _TC, base, n=20, seed=3, exclude=exclude)
    assert {0, 1} <= set(ids)  # base forced despite being in `exclude`
    assert not (set(ids) - {0, 1}) & exclude  # top-up adds none of the excluded


def test_superset_is_deterministic_under_seed():
    qs = _pool()
    a = select_superset_slice(qs, _TC, [0], n=25, seed=7)
    b = select_superset_slice(qs, _TC, [0], n=25, seed=7)
    c = select_superset_slice(qs, _TC, [0], n=25, seed=8)
    assert a == b
    assert a != c  # a different seed gives a different top-up


def test_superset_rejects_schema_ineligible_base():
    qs = _pool() + [{"question_id": 999, "db_id": "big", "difficulty": "simple"}]
    tc = {"d": 4, "big": 20}  # 'big' exceeds max_tables=5
    with pytest.raises(ValueError):
        select_superset_slice(qs, tc, [999], n=10, seed=1)


# --- the committed artifact -------------------------------------------------


def test_frozen_dev_wide_is_the_committed_size_and_sorted():
    ids = load_dev_wide_slice_ids()
    assert len(ids) == SLICE_SIZE == 250
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_dev_wide_is_a_strict_superset_of_dev():
    # Continuity: the committed 0.420 trail is re-measured inside the wider number.
    assert set(load_slice_ids()) <= set(load_dev_wide_slice_ids())


def test_dev_wide_is_strictly_disjoint_from_holdout():
    # The load-bearing guard — never widen dev into the held-out test set.
    assert not (set(load_dev_wide_slice_ids()) & set(load_holdout_slice_ids()))


def test_dev_wide_adds_no_new_ci_overlap():
    # The only prompt-CI overlap is what the dev base already shared — the top-up
    # introduces none.
    wide = set(load_dev_wide_slice_ids())
    ci = set(load_ci_slice_ids())
    assert wide & ci == set(load_slice_ids()) & ci


def test_dev_wide_is_stratified_not_all_easy():
    meta = json.loads(SLICE_FILE.read_text())["_meta"]
    mix = meta["difficulty_mix"]
    assert len(mix) >= 2
    assert sum(mix.values()) == SLICE_SIZE
    assert mix.get("simple", 0) < SLICE_SIZE


def test_dev_wide_records_its_provenance():
    crit = json.loads(SLICE_FILE.read_text())["_meta"]["criteria"]
    assert crit["seed"] == SEED
    assert crit["size"] == SLICE_SIZE
    assert crit["max_tables"] == 5
    assert crit["superset_of"] == "step3-naive-schema-dump-baseline"
    assert "step11-holdout" in crit["disjoint_strict"]
