"""The frozen Mini-Dev slice: the full upstream-curated 500, adopted as-is.

Unlike the other frozen slices this one isn't sampled — BIRD-bench already froze,
seeded, and stratified it. The load-bearing checks here are: the committed artifact
matches the downloaded source exactly (no silent edit), the loader picks up
Mini-Dev's gold-SQL corrections rather than the stale ``dev.json`` values, and
``build_bird_cases`` — the harness's entry point — produces runnable cases against
the already-downloaded ``dev_databases/`` (no extra db download needed).
"""

from __future__ import annotations

import json

from eval.datasets.bird import loader
from eval.datasets.bird.slice_minidev import SLICE_FILE, load_minidev_slice_ids
from eval.eval_bird import build_bird_cases


def test_frozen_slice_is_the_full_minidev_set():
    ids = load_minidev_slice_ids()
    assert len(ids) == 500
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)  # no duplicates


def test_frozen_ids_match_the_downloaded_source_exactly():
    ids = set(load_minidev_slice_ids())
    source_ids = {q["question_id"] for q in loader.load_minidev_questions()}
    assert ids == source_ids


def test_slice_is_stratified_across_all_three_difficulties():
    meta = json.loads(SLICE_FILE.read_text())["_meta"]
    mix = meta["difficulty_mix"]
    assert set(mix) == {"simple", "moderate", "challenging"}
    assert sum(mix.values()) == 500


def test_slice_spans_all_eleven_dbs():
    meta = json.loads(SLICE_FILE.read_text())["_meta"]
    assert len(meta["db_mix"]) == 11
    assert sum(meta["db_mix"].values()) == 500


def test_records_its_gold_sql_corrections_vs_dev_json():
    # Mini-Dev is known to fix a minority of dev.json's gold SQL; this is why
    # load_minidev_questions (not a dev.json filter) must back the runner.
    meta = json.loads(SLICE_FILE.read_text())["_meta"]
    assert meta["corrected_vs_dev_json"] > 0


def test_loader_picks_up_a_corrected_gold_sql_row():
    dev_by_id = {q["question_id"]: q for q in loader.load_dev_questions()}
    minidev = loader.load_minidev_questions()
    corrected = [
        q
        for q in minidev
        if q["question_id"] in dev_by_id
        and dev_by_id[q["question_id"]]["SQL"] != q["SQL"]
    ]
    assert corrected  # at least one row where mini-dev's gold differs from dev.json
    sample = corrected[0]
    # build_bird_cases must carry the mini-dev SQL through, not the stale dev.json one.
    cases, _ = build_bird_cases([sample["question_id"]], questions=minidev)
    assert cases[0].gold_sql == sample["SQL"]
    assert cases[0].gold_sql != dev_by_id[sample["question_id"]]["SQL"]


def test_build_bird_cases_executes_gold_against_local_dbs():
    # No extra db download needed: mini-dev's 11 dbs are the same dev_databases/
    # already present. Smoke-test a handful of cases actually execute.
    ids = load_minidev_slice_ids()[:8]
    minidev = loader.load_minidev_questions()
    cases, evidence = build_bird_cases(ids, questions=minidev)
    assert len(cases) == 8
    for case in cases:
        assert case.gold_result["columns"] is not None
        assert case.id in evidence
