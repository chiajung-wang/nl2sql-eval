"""The frozen **held-out** test slice for Step-11 optimization (overfitting guard).

Steps 1–10 only *measured* on the Step-3 slice, so its number was unbiased. Step
11 **optimizes against** that slice (tunes prompts to lift pass@1), which makes it
a *dev* set — and a number you tune against and then report on is optimistically
biased. This slice is the **held-out test set**: drawn from the same small-schema
BIRD pool (same distribution, a fair generalization test), **disjoint** from the
Step-3 dev slice *and* the prompt-CI slice, **seeded** (one fixed RNG → one
reproducible slice), and **stratified** by difficulty.

The protocol: iterate on the dev slice, then report the final lift here, touching
this slice **only once** — the moment you tune against it, it becomes dev too and
the guarantee is gone. Larger than the dev slice (100 vs 50) to tighten the
~0.05 sampling-noise floor on the final number.

Pure selection (no model): run ``python -m eval.datasets.bird.slice_step11_holdout``
to (re)generate ``slice_step11_holdout.json`` from the downloaded BIRD data.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from eval.datasets.bird.slice import MAX_TABLES, _counts, load_slice_ids, select_slice
from eval.datasets.bird.slice_ci import load_ci_slice_ids

# Frozen held-out parameters, recorded into the JSON. Distinct seed so this is an
# independent sample, and 100 questions (2× the dev slice) for a tighter number.
SLICE_SIZE = 100
SEED = 20260626

SLICE_FILE = Path(__file__).resolve().parent / "slice_step11_holdout.json"


def load_holdout_slice_ids(slice_file: Path | None = None) -> list[int]:
    """Read the frozen held-out ``question_id`` list from the JSON."""
    slice_file = slice_file or SLICE_FILE
    return json.loads(slice_file.read_text())["question_ids"]


def _excluded_ids() -> set[int]:
    """Ids the held-out must avoid: the Step-3 dev slice and the prompt-CI slice
    (both drawn from this same small-schema pool). The large slice is large-schema,
    disjoint by construction."""
    return set(load_slice_ids()) | set(load_ci_slice_ids())


def _regenerate() -> None:
    """Rebuild ``slice_step11_holdout.json`` from the downloaded BIRD data."""
    from eval.datasets.bird.loader import load_dev_questions, schema_table_counts

    questions = load_dev_questions()
    db_ids = sorted({q["db_id"] for q in questions})
    table_counts = schema_table_counts(db_ids)

    # Exclude the dev + CI ids *before* sampling, so the held-out is disjoint by
    # construction and select_slice stratifies over the remaining pool.
    exclude = _excluded_ids()
    pool = [q for q in questions if q["question_id"] not in exclude]
    ids = select_slice(
        pool, table_counts, max_tables=MAX_TABLES, n=SLICE_SIZE, seed=SEED
    )

    assert not (set(ids) & exclude), "held-out overlaps the dev/CI slices"

    eligible_dbs = {
        db: table_counts[db] for db in db_ids if table_counts[db] <= MAX_TABLES
    }
    chosen = [q for q in questions if q["question_id"] in set(ids)]
    payload = {
        "_meta": {
            "slice": "step11-holdout",
            "purpose": "Frozen, seeded, stratified HELD-OUT test slice for Step-11 "
            "optimization. Same small-schema BIRD pool as the Step-3 dev slice, but "
            "disjoint from it and from the prompt-CI slice. Tune on dev, report the "
            "final lift here — touched only once, never tuned against.",
            "criteria": {
                "max_tables": MAX_TABLES,
                "size": SLICE_SIZE,
                "seed": SEED,
                "excludes": ["step3-naive-schema-dump-baseline", "step9-prompt-ci"],
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
