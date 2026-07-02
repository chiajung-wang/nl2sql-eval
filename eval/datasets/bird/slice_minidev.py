"""The frozen **Mini-Dev** slice: BIRD's own curated 500-question SQLite subset.

Unlike the Step-3/6/9/11 slices, this one is not sampled by ``select_slice`` —
BIRD-bench already froze, seeded, and difficulty-stratified (30/50/20
simple/moderate/challenging) this 500-question subset upstream
(github.com/bird-bench/mini_dev, HuggingFace ``birdsql/bird_mini_dev``), drawn
from the same 11 dbs already under ``dev_databases/``. Adopting the *entire* set
as-is, rather than re-sampling from it, keeps its community-reported gold-SQL
corrections intact — see :func:`eval.datasets.bird.loader.load_minidev_questions`,
which must be used instead of ``load_dev_questions`` to pick those corrections up.

Recorded here anyway (rather than reading ``mini_dev_sqlite.json`` directly at run
time) for the same reason every other slice is: a frozen, version-controlled ID
list is what CLAUDE.md §5.9 requires, and it makes a future upstream revision to
the source file a visible diff instead of a silent drift.

Run ``python -m eval.datasets.bird.slice_minidev`` to (re)generate
``slice_minidev.json`` from the downloaded ``mini_dev_sqlite.json``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from eval.datasets.bird.slice import _counts

SLICE_FILE = Path(__file__).resolve().parent / "slice_minidev.json"


def load_minidev_slice_ids(slice_file: Path | None = None) -> list[int]:
    """Read the frozen Mini-Dev ``question_id`` list from ``slice_minidev.json``."""
    slice_file = slice_file or SLICE_FILE
    return json.loads(slice_file.read_text())["question_ids"]


def _regenerate() -> None:
    """Rebuild ``slice_minidev.json`` from the downloaded Mini-Dev data."""
    from eval.datasets.bird.loader import load_dev_questions, load_minidev_questions

    questions = load_minidev_questions()
    ids = sorted(q["question_id"] for q in questions)

    # Diagnostic only, not a selection criterion: how many of Mini-Dev's gold SQL
    # strings diverge from the same question_id in the full dev.json pool — those
    # are the upstream-corrected rows load_minidev_questions() must be used for.
    dev_by_id = {q["question_id"]: q for q in load_dev_questions()}
    corrected = sum(
        1
        for q in questions
        if q["question_id"] in dev_by_id
        and dev_by_id[q["question_id"]]["SQL"] != q["SQL"]
    )

    payload = {
        "_meta": {
            "slice": "minidev-sqlite-500",
            "purpose": "The full BIRD Mini-Dev SQLite subset (500 questions), "
            "adopted whole rather than re-sampled — already frozen, seeded, and "
            "difficulty-stratified upstream. A larger, community-vetted "
            "replacement/supplement for the project's own smaller hand-rolled "
            "slices, spanning both small- and large-schema dbs (schema-RAG is the "
            "appropriate default runner, not the naive dump).",
            "source": "github.com/bird-bench/mini_dev — "
            "huggingface.co/datasets/birdsql/bird_mini_dev "
            "(data/mini_dev_sqlite-00000-of-00001.json), CC-BY-SA-4.0",
            "criteria": {"size": len(ids)},
            "corrected_vs_dev_json": corrected,
            "difficulty_mix": _counts(q["difficulty"] for q in questions),
            "db_mix": _counts(q["db_id"] for q in questions),
            "generated": date.today().isoformat(),
        },
        "question_ids": ids,
    }
    SLICE_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {len(ids)} ids to {SLICE_FILE}")
    print("difficulty mix:", payload["_meta"]["difficulty_mix"])
    print("db mix:", payload["_meta"]["db_mix"])
    print("corrected vs dev.json:", corrected)


if __name__ == "__main__":
    _regenerate()
