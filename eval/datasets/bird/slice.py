"""Pick the frozen, seeded, stratified Step-3 evaluation slice.

The slice is **frozen** (checked in as an explicit ID list), **seeded** (one fixed
RNG seed → one reproducible slice), and **stratified** (difficulty proportions of
the eligible pool are preserved). It is drawn only from **smaller-schema** dbs:
with no retrieval yet the whole schema is dumped into the prompt, so large-schema
dbs would overflow context and tank accuracy for reasons unrelated to generation
quality — contaminating the baseline (CLAUDE.md §5.9, plan-step-3 pitfalls).

The selection logic here is pure (operates on plain question dicts + a db→table
count map) so it is unit-tested without the full BIRD download. Run this module
as ``python -m eval.datasets.bird.slice`` to (re)generate ``slice_step3.json``
from the downloaded data.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

# The frozen selection parameters. Changing any of these changes the slice, so
# they are recorded into slice_step3.json alongside the chosen IDs.
MAX_TABLES = 5
SLICE_SIZE = 50
SEED = 20260611

SLICE_FILE = Path(__file__).resolve().parent / "slice_step3.json"


def _largest_remainder(sizes: Mapping[str, int], n: int) -> dict[str, int]:
    """Allocate ``n`` across strata proportional to ``sizes`` (exact sum ``n``).

    Floors each proportional share, then hands the leftover one at a time to the
    strata with the largest fractional remainders (ties broken by key, for
    determinism). With ``n <= sum(sizes)`` every allocation stays within its
    stratum, so the result is always a valid exact split.
    """
    total = sum(sizes.values())
    if total == 0 or n == 0:
        return {key: 0 for key in sizes}
    raw = {key: n * size / total for key, size in sizes.items()}
    alloc = {key: int(math.floor(value)) for key, value in raw.items()}
    leftover = n - sum(alloc.values())
    by_remainder = sorted(sizes, key=lambda key: (-(raw[key] - alloc[key]), key))
    for key in by_remainder[:leftover]:
        alloc[key] += 1
    return alloc


def select_slice(
    questions: Sequence[Mapping[str, Any]],
    table_counts: Mapping[str, int],
    *,
    max_tables: int = MAX_TABLES,
    min_tables: int = 0,
    n: int = SLICE_SIZE,
    seed: int = SEED,
) -> list[int]:
    """Return the frozen slice as a sorted list of ``question_id``s.

    Eligible questions are those whose tagged db has ``min_tables <= count <=
    max_tables`` tables (Step 3 uses ``max_tables=5``; Step 6's large-schema slice
    uses ``min_tables=6`` to draw exactly the dbs where retrieval earns its keep).
    ``n`` of them are sampled with a fixed ``seed``, stratified so the slice keeps
    the eligible pool's difficulty mix. Deterministic: same inputs + seed → same
    IDs, every time.
    """
    eligible = [
        q
        for q in questions
        if min_tables <= table_counts.get(q["db_id"], math.inf) <= max_tables
    ]
    n = min(n, len(eligible))

    by_difficulty: dict[str, list[Mapping[str, Any]]] = {}
    for q in eligible:
        by_difficulty.setdefault(q["difficulty"], []).append(q)

    alloc = _largest_remainder({diff: len(qs) for diff, qs in by_difficulty.items()}, n)

    rng = random.Random(seed)
    chosen: list[str] = []
    for difficulty in sorted(by_difficulty):
        pool = sorted(by_difficulty[difficulty], key=lambda q: q["question_id"])
        chosen += [q["question_id"] for q in rng.sample(pool, alloc[difficulty])]
    return sorted(chosen)


def load_slice_ids(slice_file: Path | None = None) -> list[int]:
    """Read the frozen ``question_id`` list from ``slice_step3.json``."""
    slice_file = slice_file or SLICE_FILE
    return json.loads(slice_file.read_text())["question_ids"]


def _regenerate() -> None:
    """Rebuild ``slice_step3.json`` from the downloaded BIRD data."""
    from eval.datasets.bird.loader import load_dev_questions, schema_table_counts

    questions = load_dev_questions()
    db_ids = sorted({q["db_id"] for q in questions})
    table_counts = schema_table_counts(db_ids)
    ids = select_slice(questions, table_counts)

    eligible_dbs = {
        db: table_counts[db] for db in db_ids if table_counts[db] <= MAX_TABLES
    }
    chosen = [q for q in questions if q["question_id"] in set(ids)]
    payload = {
        "_meta": {
            "slice": "step3-naive-schema-dump-baseline",
            "purpose": "Frozen, seeded, stratified Step-3 slice from smaller-schema "
            "BIRD dbs. Anchors the first pass@1 number; small-schema-first keeps the "
            "naive schema-dump baseline trustworthy (no context-overflow effects).",
            "criteria": {"max_tables": MAX_TABLES, "size": SLICE_SIZE, "seed": SEED},
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


def _counts(values: Any) -> dict[str, int]:
    from collections import Counter

    return dict(sorted(Counter(values).items()))


if __name__ == "__main__":
    _regenerate()
