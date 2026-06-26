"""Step-11 #112: schema enrichment A/B — naive DDL dump vs DDL + FK + sample rows.

The error analysis (#111) named **wrong tables / wrong join path** as the dominant
genuine-failure bucket. This A/Bs the fix: same template, same model, same slice —
only the **schema representation** changes, naive dump vs :func:`enriched_schema`
(surfaced foreign keys + sample rows). It reports pass@1 naive vs enriched **and**
the join/table failure-bucket movement (proving the lever hit its target, not just
the headline), via the same deterministic AST tagger the diagnostic uses.

Run on **dev** (the Step-3 slice) to iterate, then on the **held-out** slice to
validate the lift generalizes (the dev/held-out protocol — overfitting guard):

    uv run python -m eval.eval_bird_schema                 # dev (Step-3) slice
    SLICE=holdout uv run python -m eval.eval_bird_schema   # held-out slice
    uv run python -m eval.eval_bird_schema --dry-run       # run + print, no write
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from functools import cache

from dotenv import load_dotenv

from eval.datasets.bird.enrich import enriched_schema
from eval.datasets.bird.slice_step11_holdout import load_holdout_slice_ids
from eval.diagnose_bird import categorize
from eval.eval_bird import (
    DIALECT,
    RESULTS_PATH,
    _engine,
    _git_commit,
    _schema,
    build_bird_cases,
    slice_id,
)
from eval.eval_bird_twin import append_results
from eval.harness import Case, RunOne, batch_session_id, run_batch
from eval.metrics import BatchReport, summary_lines
from eval.model_select import model_id
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState
from nl2sql.prompts import PROMPT_VERSION

# Join-path failures are the target bucket the diagnostic named.
_JOIN_TAGS = ("table_mismatch", "join_mismatch")

# The enrichment components on the enriched arm: ``ENRICH`` = both (default) | fks
# | samples — so the A/B can isolate the surfaced join paths from the (possibly
# distracting) sample rows.
_MODES = {"both": (True, True), "fks": (True, False), "samples": (False, True)}


def enrich_mode() -> str:
    mode = os.environ.get("ENRICH", "both").strip()
    return mode if mode in _MODES else "both"


@cache
def _enriched(db_id: str, mode: str) -> str:
    fks, samples = _MODES[mode]
    return enriched_schema(_engine(db_id), fks=fks, samples=samples)


def make_run_one(evidence: dict[str, str], enriched: bool, model: str) -> RunOne:
    """Single-shot (pass@1) runner; ``enriched`` swaps the schema representation."""
    mode = enrich_mode()
    schema_fn = (lambda db: _enriched(db, mode)) if enriched else _schema

    def run_one(case: Case) -> RunState:
        return run_pipeline(
            case.question,
            schema=schema_fn(case.db_id),
            engine=_engine(case.db_id),
            db_id=case.db_id,
            dialect=DIALECT,
            evidence=evidence.get(case.id, ""),
            model=model,
        )

    return run_one


def join_bucket(report: BatchReport, by_id: dict[str, Case]) -> int:
    """How many failures involve a wrong table / wrong join path (the target)."""
    n = 0
    for r in report.results:
        if r.correct:
            continue
        tags = categorize(by_id[r.case_id].gold_sql, r.candidate_sql)
        if any(t in _JOIN_TAGS for t in tags):
            n += 1
    return n


def results_row(
    naive: BatchReport,
    enr: BatchReport,
    *,
    slice_name: str,
    mode: str,
    model: str,
    commit: str,
) -> str:
    lift = enr.accuracy - naive.accuracy
    number = (
        f"{naive.accuracy:.3f} ({naive.n_correct}/{naive.total}) → "
        f"{enr.accuracy:.3f} ({enr.n_correct}/{enr.total}) [lift {lift:+.3f}]"
    )
    return (
        f"| {date.today().isoformat()} | 11 | schema enrichment [{mode}] "
        f"(pass@1, {slice_name}) | {number} | {model} | {slice_name} | "
        f"{PROMPT_VERSION} | {commit} |"
    )


def results_prose(
    naive: BatchReport,
    enr: BatchReport,
    *,
    naive_join: int,
    enr_join: int,
    slice_name: str,
    model: str,
) -> str:
    lift = enr.accuracy - naive.accuracy
    verdict = (
        "a lift"
        if lift > 0.0
        else "no lift (flat within noise)"
        if lift >= -0.02
        else "a regression"
    )
    bucket = (
        "shrank"
        if enr_join < naive_join
        else "grew"
        if enr_join > naive_join
        else "held"
    )
    return (
        f"**Step 11 (#112) — schema enrichment [{enrich_mode()}] on `{slice_name}` "
        f"(pass@1).** Same template, same model, only the schema representation "
        f"changes (naive DDL dump vs surfaced FK join paths / sample rows). pass@1 "
        f"**{naive.accuracy:.3f} ({naive.n_correct}/{naive.total})** → "
        f"**{enr.accuracy:.3f} ({enr.n_correct}/{enr.total})** — **{lift:+.3f}**, "
        f"{verdict}. The targeted wrong-table/wrong-join bucket {bucket} "
        f"**{naive_join} → {enr_join}**. Reproduce with "
        f"`uv run python -m eval.eval_bird_schema` (`ENRICH=fks|samples`, "
        f"`SLICE=holdout`)."
    )


def _slice_for(args: list[str]) -> tuple[list[int] | None, str]:
    """Dev (Step-3, default) or held-out via ``SLICE=holdout`` / ``--holdout``."""
    if os.environ.get("SLICE") == "holdout" or "--holdout" in args:
        return load_holdout_slice_ids(), "step11-holdout"
    return None, slice_id()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    model = model_id()
    ids, slice_name = _slice_for(args)
    cases, evidence = build_bird_cases(slice_ids=ids)
    by_id = {c.id: c for c in cases}

    print(f"=== naive DDL dump ({len(cases)} questions · {slice_name} · {model}) ===")
    naive = run_batch(
        cases,
        make_run_one(evidence, enriched=False, model=model),
        session_id=batch_session_id(
            f"bird-schema-naive-{slice_name}",
            model=model,
            prompt_version=PROMPT_VERSION,
        ),
    )
    print("\n".join(summary_lines(naive)))

    print(f"\n=== enriched ({len(cases)} questions · {slice_name} · {model}) ===")
    enr = run_batch(
        cases,
        make_run_one(evidence, enriched=True, model=model),
        session_id=batch_session_id(
            f"bird-schema-enriched-{slice_name}",
            model=model,
            prompt_version=PROMPT_VERSION,
        ),
    )
    print("\n".join(summary_lines(enr)))

    naive_join, enr_join = join_bucket(naive, by_id), join_bucket(enr, by_id)
    print("\n=== schema-enrichment lift ===")
    print(f"naive    pass@1: {naive.accuracy:.3f} ({naive.n_correct}/{naive.total})")
    print(f"enriched pass@1: {enr.accuracy:.3f} ({enr.n_correct}/{enr.total})")
    print(f"lift:            {enr.accuracy - naive.accuracy:+.3f}")
    print(f"join/table failure bucket: {naive_join} → {enr_join}")

    row = results_row(
        naive,
        enr,
        slice_name=slice_name,
        mode=enrich_mode(),
        model=model,
        commit=_git_commit(),
    )
    prose = results_prose(
        naive,
        enr,
        naive_join=naive_join,
        enr_join=enr_join,
        slice_name=slice_name,
        model=model,
    )
    print("\nRESULTS.md row:\n" + row)
    if write:
        append_results(row, prose)
        print(f"\nappended to {RESULTS_PATH.name}")
    from nl2sql import obs

    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
