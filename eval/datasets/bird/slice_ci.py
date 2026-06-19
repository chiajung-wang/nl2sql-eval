"""Pick the frozen, seeded, stratified **prompt-CI** slice (Step 9).

The slice prompt-CI runs on every change to ``prompts/``. Same discipline as the
Step-3 slice — frozen ID list, one fixed seed, difficulty strata preserved — but
deliberately **small**: it is the **cost guard**. Each push runs the slice twice
(base prompt vs PR prompt), each a pass@k run, so per-push LLM cost scales with
``SLICE_SIZE × k × 2``. A frozen 12-question slice keeps that bounded while
staying stratified, so a delta means a real regression, not sampling on an
accidentally-all-easy subset (plan-step-9 pitfalls).

Drawn from the same small-schema dbs as Step 3 (``max_tables=5``): with the naive
schema dump these never overflow context, so a prompt-quality delta is measured
cleanly, not confounded by truncation. The selection reuses the pure
``select_slice`` from ``slice.py`` (so it is unit-tested without the BIRD
download). Run ``python -m eval.datasets.bird.slice_ci`` to (re)generate
``slice_ci.json`` from the downloaded data.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from eval.datasets.bird.slice import MAX_TABLES, _counts, select_slice

# The frozen prompt-CI selection parameters, recorded into slice_ci.json. Small
# by design (the cost guard); the seed is distinct from the Step-3/6 slices so it
# is an independent sample, not a prefix of an existing one.
SLICE_SIZE = 12
SEED = 20260619

SLICE_FILE = Path(__file__).resolve().parent / "slice_ci.json"


def load_ci_slice_ids(slice_file: Path | None = None) -> list[int]:
    """Read the frozen prompt-CI ``question_id`` list from ``slice_ci.json``."""
    slice_file = slice_file or SLICE_FILE
    return json.loads(slice_file.read_text())["question_ids"]


def _regenerate() -> None:
    """Rebuild ``slice_ci.json`` from the downloaded BIRD data."""
    from eval.datasets.bird.loader import load_dev_questions, schema_table_counts

    questions = load_dev_questions()
    db_ids = sorted({q["db_id"] for q in questions})
    table_counts = schema_table_counts(db_ids)
    ids = select_slice(
        questions,
        table_counts,
        max_tables=MAX_TABLES,
        n=SLICE_SIZE,
        seed=SEED,
    )

    eligible_dbs = {
        db: table_counts[db] for db in db_ids if table_counts[db] <= MAX_TABLES
    }
    chosen = [q for q in questions if q["question_id"] in set(ids)]
    payload = {
        "_meta": {
            "slice": "step9-prompt-ci",
            "purpose": "Frozen, seeded, stratified Step-9 prompt-CI slice. Small by "
            "design — the cost guard: prompt-CI runs it twice per push (base vs PR "
            "prompt), so cost scales with size × k × 2. Drawn from the same "
            "small-schema BIRD dbs as Step 3 (max_tables=5) so the naive dump never "
            "overflows context and a prompt-quality delta is measured cleanly.",
            "criteria": {
                "max_tables": MAX_TABLES,
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
