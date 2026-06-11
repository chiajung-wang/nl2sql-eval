"""BIRD loader + frozen-slice selection (Step 3, Issue 2).

The selection logic is pure and tested on synthetic inputs; the loader is tested
against a tiny synthetic SQLite db — both run with **no BIRD download**. The
end-to-end checks (load → execute gold → score) and the frozen-slice integrity
checks run only when the real data is present, and ``skip`` otherwise, so CI stays
green without gigabytes of benchmark data.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from eval.compare import Verdict, compare
from eval.datasets.bird import loader
from eval.datasets.bird import slice as bird_slice
from eval.datasets.bird.loader import (
    bird_data_dir,
    get_engine,
    run_query,
    schema_text,
    table_count,
)
from eval.datasets.bird.slice import MAX_TABLES, _largest_remainder, select_slice

# --- pure selection logic (no download) ------------------------------------

_SMALL = "small_db"
_BIG = "big_db"
_TABLE_COUNTS = {_SMALL: 2, _BIG: 20}


def _synthetic_questions() -> list[dict]:
    qs: list[dict] = []
    qid = 0
    for db, base in ((_SMALL, 0), (_BIG, 100)):
        for difficulty in ("simple", "moderate", "challenging"):
            for _ in range(10):
                qs.append(
                    {"question_id": base + qid, "db_id": db, "difficulty": difficulty}
                )
                qid += 1
    return qs


def test_slice_only_includes_small_schema_dbs():
    ids = select_slice(
        _synthetic_questions(), _TABLE_COUNTS, max_tables=5, n=12, seed=1
    )
    chosen = {q["question_id"]: q for q in _synthetic_questions()}
    assert all(chosen[i]["db_id"] == _SMALL for i in ids)


def test_slice_is_exact_size_and_deterministic():
    args = (_synthetic_questions(), _TABLE_COUNTS)
    first = select_slice(*args, max_tables=5, n=12, seed=1)
    again = select_slice(*args, max_tables=5, n=12, seed=1)
    other = select_slice(*args, max_tables=5, n=12, seed=99)
    assert len(first) == 12
    assert first == again  # same seed → identical slice
    assert first != other  # a different seed yields a different slice


def test_slice_preserves_difficulty_stratification():
    qs = _synthetic_questions()
    ids = set(select_slice(qs, _TABLE_COUNTS, max_tables=5, n=12, seed=1))
    mix = Counter(q["difficulty"] for q in qs if q["question_id"] in ids)
    # eligible pool is 10/10/10 across difficulties → 12 splits evenly to 4/4/4.
    assert mix == {"simple": 4, "moderate": 4, "challenging": 4}


def test_largest_remainder_sums_to_n_and_stays_in_bounds():
    alloc = _largest_remainder({"a": 10, "b": 5, "c": 1}, 7)
    assert sum(alloc.values()) == 7
    assert all(alloc[k] <= size for k, size in {"a": 10, "b": 5, "c": 1}.items())


def test_slice_caps_at_available_when_n_exceeds_pool():
    ids = select_slice(
        _synthetic_questions(), _TABLE_COUNTS, max_tables=5, n=999, seed=1
    )
    assert len(ids) == 30  # only the 30 small-schema questions exist


# --- loader against a synthetic SQLite db (no download) --------------------


@pytest.fixture
def mini_data_dir(tmp_path: Path) -> Path:
    db_dir = tmp_path / "dev_databases" / "mini"
    db_dir.mkdir(parents=True)
    con = sqlite3.connect(db_dir / "mini.sqlite")
    con.executescript(
        "CREATE TABLE t (id INTEGER, name TEXT);"
        "INSERT INTO t VALUES (1, 'a'), (2, 'b');"
    )
    con.commit()
    con.close()
    return tmp_path


def test_loader_reads_schema_and_runs_queries(mini_data_dir: Path):
    engine = get_engine("mini", mini_data_dir)
    assert table_count(engine) == 1
    assert "CREATE TABLE" in schema_text(engine)
    result = run_query(engine, "SELECT id, name FROM t ORDER BY id")
    assert result == {"columns": ["id", "name"], "rows": [(1, "a"), (2, "b")]}


def test_loader_is_read_only(mini_data_dir: Path):
    engine = get_engine("mini", mini_data_dir)
    with pytest.raises(OperationalError, match="readonly"):
        run_query(engine, "INSERT INTO t VALUES (3, 'c')")


def test_missing_db_is_a_clear_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="BIRD db 'nope' not found"):
        get_engine("nope", tmp_path)


# --- real-data integration (skips without the BIRD download) ----------------

_DATA_DIR = bird_data_dir()
_HAS_BIRD = (_DATA_DIR / "dev.json").exists()
_needs_bird = pytest.mark.skipif(not _HAS_BIRD, reason="BIRD data not downloaded")


@_needs_bird
def test_one_bird_question_loads_executes_and_scores_end_to_end():
    # The AC: a single BIRD question can be loaded, executed against its tagged
    # db, and scored via compare.py. Gold-vs-gold must be correct; a perturbed
    # candidate must be incorrect — proving the path actually discriminates.
    ids = set(bird_slice.load_slice_ids())
    questions = loader.load_dev_questions()
    q = next(q for q in questions if q["question_id"] in ids)
    engine = get_engine(q["db_id"])
    gold = run_query(engine, q["SQL"])

    assert compare(gold, gold, q["SQL"]).verdict is Verdict.CORRECT
    perturbed = {
        "columns": gold["columns"],
        "rows": gold["rows"][:-1] + [("__wrong__",)],
    }
    if gold["rows"]:
        assert compare(gold, perturbed, q["SQL"]).verdict is Verdict.INCORRECT


@_needs_bird
def test_frozen_slice_is_valid_and_small_schema_only():
    ids = bird_slice.load_slice_ids()
    questions = loader.load_dev_questions()
    by_id = {q["question_id"]: q for q in questions}

    assert len(ids) == len(set(ids))  # no dupes
    assert all(i in by_id for i in ids)  # every id is a real BIRD question

    slice_dbs = {by_id[i]["db_id"] for i in ids}
    counts = loader.schema_table_counts(sorted(slice_dbs))
    assert all(counts[db] <= MAX_TABLES for db in slice_dbs)
