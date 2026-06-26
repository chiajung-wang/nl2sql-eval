"""Score the frozen BIRD slice → the first real pass@1, logged to RESULTS.md.

The Phase-1 Definition of Done: the harness (validated on payments) pointed at a
frozen, seeded, small-schema BIRD slice through the **import-shared** pipeline and
the **Step-2 comparator**. Each question runs against its own tagged SQLite db;
the gold SQL is executed to materialize the gold result set, the pipeline produces
a candidate, and ``compare()`` scores it. The result is appended to ``RESULTS.md``
with full config (CLAUDE.md §6).

This pass@1 is the **naive schema-dump baseline** — the whole schema is dumped
into the prompt (no retrieval yet), SQLite dialect, with the BIRD evidence hint.
A modest number is the "before" Step-6 retrieval will lift.

    uv run python -m eval.eval_bird            # run + append RESULTS.md
    uv run python -m eval.eval_bird --dry-run  # run + print, no RESULTS.md write
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import date
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import Engine

from eval.datasets.bird import loader
from eval.datasets.bird.slice import SLICE_FILE, load_slice_ids
from eval.harness import Case, batch_session_id, run_batch
from eval.metrics import BatchReport, summary_lines
from eval.model_select import model_id
from nl2sql import obs
from nl2sql.pipeline.generate import DEFAULT_MODEL
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState
from nl2sql.prompts import PROMPT_VERSION

DIALECT = "SQLite"
RESULTS_PATH = Path(__file__).resolve().parents[1] / "RESULTS.md"


@cache
def _engine(db_id: str) -> Engine:
    return loader.get_engine(db_id)


@cache
def _schema(db_id: str) -> str:
    return loader.schema_text(_engine(db_id))


def build_bird_cases(
    slice_ids: list[int] | None = None,
) -> tuple[list[Case], dict[str, str]]:
    """Build a :class:`Case` per slice question (gold executed against its tagged
    db) plus the per-question evidence map. ``slice_ids`` defaults to the frozen
    Step-3 slice; the Step-6 large-schema runner passes its own slice. Gold
    execution is SQLite-only — no API — so this is testable offline whenever the
    BIRD data is present."""
    wanted = set(slice_ids if slice_ids is not None else load_slice_ids())
    questions = [q for q in loader.load_dev_questions() if q["question_id"] in wanted]
    cases: list[Case] = []
    evidence: dict[str, str] = {}
    for q in questions:
        cid = str(q["question_id"])
        gold = loader.run_query(_engine(q["db_id"]), q["SQL"])
        cases.append(
            Case(
                id=cid,
                question=q["question"],
                db_id=q["db_id"],
                gold_sql=q["SQL"],
                gold_result=gold,
                difficulty=q["difficulty"],
            )
        )
        evidence[cid] = q.get("evidence") or ""
    return cases, evidence


def make_run_one(evidence: dict[str, str], model: str = DEFAULT_MODEL):
    """Bind the import-shared pipeline for the BIRD path: SQLite dialect + the
    per-question evidence hint, against each case's tagged read-only db. ``model``
    selects the generator (the ``MODEL`` env override resolves to it)."""

    def run_one(case: Case) -> RunState:
        return run_pipeline(
            case.question,
            schema=_schema(case.db_id),
            engine=_engine(case.db_id),
            db_id=case.db_id,
            dialect=DIALECT,
            evidence=evidence.get(case.id, ""),
            model=model,
        )

    return run_one


def slice_id() -> str:
    """The frozen slice's name, recorded in the RESULTS.md row."""
    return json.loads(SLICE_FILE.read_text())["_meta"]["slice"]


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    return proc.stdout.strip() or "unknown"


def results_row(
    report: BatchReport, *, model: str, prompt_version: str, commit: str
) -> str:
    """Format the RESULTS.md log row for this run (CLAUDE.md §6 — full config)."""
    number = f"{report.pass_at_1:.3f} ({report.n_correct}/{report.total})"
    return (
        f"| {date.today().isoformat()} | 3 | pass@1 | {number} | "
        f"{model} | {slice_id()} | {prompt_version} | {commit} |"
    )


def append_results(row: str, results_path: Path = RESULTS_PATH) -> None:
    """Append ``row`` to the RESULTS.md log, retiring the placeholder table row."""
    lines = [
        ln
        for ln in results_path.read_text().splitlines()
        if not ln.strip().startswith("| _—_")
    ]
    results_path.write_text("\n".join(lines).rstrip() + "\n" + row + "\n")


def main(argv: list[str] | None = None) -> int:
    write = "--dry-run" not in (argv if argv is not None else sys.argv[1:])
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    model = model_id()
    cases, evidence = build_bird_cases()
    print(
        f"scoring {len(cases)} BIRD questions ({DIALECT}, naive schema dump) "
        f"on `{model}`…"
    )
    report = run_batch(
        cases,
        make_run_one(evidence, model),
        session_id=batch_session_id(
            "bird-naive", model=model, prompt_version=PROMPT_VERSION
        ),
    )

    print("\n" + "\n".join(summary_lines(report)))
    row = results_row(
        report, model=model, prompt_version=PROMPT_VERSION, commit=_git_commit()
    )
    print("\nRESULTS.md row:\n" + row)
    if write:
        append_results(row)
        print(f"\nappended to {RESULTS_PATH.name}")
    # Short-lived job: export buffered Langfuse spans before exit. A no-op offline
    # and redundant with the SDK's atexit flush, but makes export deterministic.
    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
