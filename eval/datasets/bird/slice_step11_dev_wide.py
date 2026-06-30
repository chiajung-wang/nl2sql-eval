"""The frozen **wide dev** slice for Step-11 marginal levers (#133).

The 50-question Step-3 dev slice has a ~0.05 sampling-noise floor, so most of the
levers Step 11 considered (FK-only enrichment −0.020, the deferred FK-soundness
A/B) landed *inside* it — inconclusive, not negative. This slice widens the dev
substrate so a **+0.03** effect is distinguishable from jitter, which is the
prerequisite for the table-selection levers (#134/#135) that live in exactly that
marginal regime.

Design — a strict **superset** of the dev slice:

- **Contains all 50 Step-3 dev ids** (``select_superset_slice`` forces them in), so
  the committed 0.420 trail is re-measured *inside* the wider number, not abandoned.
- **Widens to 250** (5× dev). At p≈0.45 the per-question sampling SE falls from
  ~0.070 (n=50) to ~0.031 (n=250) — ~2.2× tighter, putting the 1σ floor near the
  ±0.03 a marginal lever needs to clear.
- **Strictly disjoint from the held-out slice** — the load-bearing guard, so the
  wider dev number never burns the generalization test. The top-up is also kept
  clear of the prompt-CI slice; the only CI overlap is the **3 questions the dev
  base already shares with prompt-CI** (the dev slice was never CI-disjoint), which
  the superset preserves rather than dropping — no *new* overlap is introduced.
- **Seeded + stratified** by difficulty over the same small-schema pool — same
  distribution as dev, so it is a fair widening, not a different population.

Caveat (inherited from the plan): the small-schema pool is only 4 dbs, so this is
*question-level* widening, not db-level — the wider number tightens sampling noise,
it does not add schema diversity.

Pure selection (no model): run ``python -m eval.datasets.bird.slice_step11_dev_wide``
to (re)generate ``slice_step11_dev_wide.json`` from the downloaded BIRD data.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from eval.datasets.bird.slice import (
    MAX_TABLES,
    _counts,
    load_slice_ids,
    select_superset_slice,
)
from eval.datasets.bird.slice_ci import load_ci_slice_ids
from eval.datasets.bird.slice_step11_holdout import load_holdout_slice_ids

# Frozen wide-dev parameters, recorded into the JSON. Distinct seed (independent
# top-up sample); 250 = 5× the dev slice, sized for a ~±0.03 sampling SE.
SLICE_SIZE = 250
SEED = 20260630

SLICE_FILE = Path(__file__).resolve().parent / "slice_step11_dev_wide.json"


def load_dev_wide_slice_ids(slice_file: Path | None = None) -> list[int]:
    """Read the frozen wide-dev ``question_id`` list from the JSON."""
    slice_file = slice_file or SLICE_FILE
    return json.loads(slice_file.read_text())["question_ids"]


def _excluded_ids() -> set[int]:
    """Ids the wide-dev must avoid: the held-out test slice and the prompt-CI slice
    (both drawn from this same small-schema pool). The dev slice is *not* excluded —
    it is force-included as the superset base."""
    return set(load_holdout_slice_ids()) | set(load_ci_slice_ids())


def _regenerate() -> None:
    """Rebuild ``slice_step11_dev_wide.json`` from the downloaded BIRD data."""
    from eval.datasets.bird.loader import load_dev_questions, schema_table_counts

    questions = load_dev_questions()
    db_ids = sorted({q["db_id"] for q in questions})
    table_counts = schema_table_counts(db_ids)

    base = load_slice_ids()  # the frozen Step-3 dev slice — the superset base
    holdout = set(load_holdout_slice_ids())
    ci = set(load_ci_slice_ids())
    exclude = _excluded_ids()  # holdout ∪ CI — constrains the top-up only
    ids = select_superset_slice(
        questions,
        table_counts,
        base,
        max_tables=MAX_TABLES,
        n=SLICE_SIZE,
        seed=SEED,
        exclude=frozenset(exclude),
    )

    ids_set = set(ids)
    assert set(base) <= ids_set, "wide-dev must contain every dev id (superset)"
    # Held-out disjointness is the load-bearing guard — strict.
    assert not (ids_set & holdout), "wide-dev overlaps the held-out slice"
    # CI overlap must be only what the dev base already had — the top-up adds none.
    assert ids_set & ci == set(base) & ci, "wide-dev introduced new prompt-CI overlap"

    eligible_dbs = {
        db: table_counts[db] for db in db_ids if table_counts[db] <= MAX_TABLES
    }
    chosen = [q for q in questions if q["question_id"] in set(ids)]
    payload = {
        "_meta": {
            "slice": "step11-dev-wide",
            "purpose": "Frozen, seeded, stratified WIDE DEV slice for Step-11 "
            "marginal levers. A strict superset of the Step-3 dev slice (keeps the "
            "0.420 trail), widened to 250 for a ~±0.03 sampling SE; disjoint from "
            "the held-out and prompt-CI slices, so it stays a dev set.",
            "criteria": {
                "max_tables": MAX_TABLES,
                "size": SLICE_SIZE,
                "seed": SEED,
                "superset_of": "step3-naive-schema-dump-baseline",
                "disjoint_strict": ["step11-holdout"],
                "topup_excludes": ["step11-holdout", "step9-prompt-ci"],
                "note": "Top-up adds no new prompt-CI overlap; the only CI overlap "
                "is the 3 ids the dev base already shares with prompt-CI.",
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
