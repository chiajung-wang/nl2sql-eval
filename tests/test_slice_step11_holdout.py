"""The frozen Step-11 held-out slice — disjoint, seeded, stratified (overfit guard).

The selection logic is the pure ``select_slice`` covered elsewhere; here we lock
the committed artifact's load-bearing invariants: it exists at the committed size,
it is **disjoint** from the dev (Step-3) and prompt-CI slices it must not leak
from, and it stays stratified (not accidentally all-easy).
"""

from __future__ import annotations

import json

from eval.datasets.bird.slice import load_slice_ids
from eval.datasets.bird.slice_ci import load_ci_slice_ids
from eval.datasets.bird.slice_step11_holdout import (
    SEED,
    SLICE_FILE,
    SLICE_SIZE,
    load_holdout_slice_ids,
)


def test_frozen_holdout_is_the_committed_size_and_sorted():
    ids = load_holdout_slice_ids()
    assert len(ids) == SLICE_SIZE == 100
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)  # no dupes


def test_holdout_is_disjoint_from_dev_and_ci():
    # The whole point: a number you tune against (dev/CI) must not appear in the
    # set you report the final lift on.
    holdout = set(load_holdout_slice_ids())
    assert not (holdout & set(load_slice_ids()))  # Step-3 dev slice
    assert not (holdout & set(load_ci_slice_ids()))  # prompt-CI slice


def test_holdout_is_stratified_not_all_easy():
    meta = json.loads(SLICE_FILE.read_text())["_meta"]
    mix = meta["difficulty_mix"]
    assert len(mix) >= 2
    assert sum(mix.values()) == SLICE_SIZE
    assert mix.get("simple", 0) < SLICE_SIZE  # not exclusively simple


def test_holdout_records_its_seed_and_exclusions():
    crit = json.loads(SLICE_FILE.read_text())["_meta"]["criteria"]
    assert crit["seed"] == SEED
    assert crit["size"] == SLICE_SIZE
    assert crit["max_tables"] == 5
    assert "step3-naive-schema-dump-baseline" in crit["excludes"]
    assert "step9-prompt-ci" in crit["excludes"]
