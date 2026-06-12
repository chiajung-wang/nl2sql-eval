"""Pick the frozen, seeded, stratified Step-6 **large-schema** evaluation slice.

Same discipline as the Step-3 slice (frozen ID list, one fixed seed, difficulty
strata preserved) but drawn from the **large-schema** dbs — those with *more*
tables than the Step-3 cap — because that is exactly where dumping the whole
schema into the prompt overflows context and schema-RAG earns its keep. The
naive-dump → retrieval **lift** is measured on this slice (Step 6 DoD).

The selection reuses the pure ``select_slice`` from ``slice.py`` (with a
``min_tables`` floor instead of a ceiling), so it is unit-tested without the BIRD
download. Run ``python -m eval.datasets.bird.slice_large`` to (re)generate
``slice_step6.json`` from the downloaded data.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from eval.datasets.bird.slice import _counts, select_slice

# The frozen Step-6 selection parameters, recorded into slice_step6.json. The
# floor (``MIN_TABLES``) is one above the Step-3 ceiling (5), so the two slices
# are disjoint by schema size: small-schema baseline vs large-schema lift.
MIN_TABLES = 6
MAX_TABLES = 10_000  # no ceiling — every db at/above the floor is eligible
SLICE_SIZE = 40
SEED = 20260613

SLICE_FILE = Path(__file__).resolve().parent / "slice_step6.json"


def load_large_slice_ids(slice_file: Path | None = None) -> list[int]:
    """Read the frozen Step-6 ``question_id`` list from ``slice_step6.json``."""
    slice_file = slice_file or SLICE_FILE
    return json.loads(slice_file.read_text())["question_ids"]


def _regenerate() -> None:
    """Rebuild ``slice_step6.json`` from the downloaded BIRD data."""
    from eval.datasets.bird.loader import load_dev_questions, schema_table_counts

    questions = load_dev_questions()
    db_ids = sorted({q["db_id"] for q in questions})
    table_counts = schema_table_counts(db_ids)
    ids = select_slice(
        questions,
        table_counts,
        min_tables=MIN_TABLES,
        max_tables=MAX_TABLES,
        n=SLICE_SIZE,
        seed=SEED,
    )

    eligible_dbs = {
        db: table_counts[db] for db in db_ids if MIN_TABLES <= table_counts[db]
    }
    chosen = [q for q in questions if q["question_id"] in set(ids)]
    payload = {
        "_meta": {
            "slice": "step6-large-schema-retrieval-lift",
            "purpose": "Frozen, seeded, stratified Step-6 slice from larger-schema "
            "BIRD dev dbs (above Step-3's 5-table cap, up to 14 tables). The "
            "naive-dump → schema-RAG retrieval lift is measured on this slice. "
            "Note: these dev dbs still FIT the model's context, so the measured "
            "lift quantifies retrieval's real cost/benefit here rather than "
            "assuming overflow — and on this slice it comes out negative.",
            "criteria": {
                "min_tables": MIN_TABLES,
                "size": SLICE_SIZE,
                "seed": SEED,
            },
            "eligible_dbs": eligible_dbs,
            "difficulty_mix": _counts(q["difficulty"] for q in chosen),
            "db_mix": _counts(q["db_id"] for q in chosen),
            "generated": date.today().isoformat(),
        },
        "question_ids": ids,
    }
    SLICE_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {len(ids)} ids to {SLICE_FILE}")
    print("difficulty mix:", payload["_meta"]["difficulty_mix"])
    print("db mix:", payload["_meta"]["db_mix"])


if __name__ == "__main__":
    _regenerate()
