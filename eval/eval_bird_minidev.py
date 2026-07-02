"""pass@1 on the frozen Mini-Dev slice, via schema-RAG.

BIRD Mini-Dev (see ``eval/datasets/bird/slice_minidev.py``) is a 500-question,
upstream-curated, difficulty-stratified subset spanning both small- and
large-schema dbs from the same dev pool. Unlike Step 3's naive-dump baseline, this
runs the **schema-RAG** arm (``retrieve`` selects tables, same as Step 6+) since
Mini-Dev includes large-schema dbs a full dump would overflow — this is meant as a
larger, community-vetted number for the *current* pipeline, not a retrieval-lift
measurement (that's Step 6's job on the small `slice_step6` slice).

Reuses ``eval_bird_rag.make_rag_run_one``, so every A/B axis it already wires
(``LINK_STRATEGY``, ``SOUNDNESS``, ``RETRY_BUDGET``, ``LITERAL_STEER``,
``METADATA_SOURCE``) works unchanged here — this is the same schema-RAG path, over
a different (larger, corrected-gold) question pool.

    uv run python -m eval.eval_bird_minidev             # run + append RESULTS.md
    uv run python -m eval.eval_bird_minidev --dry-run   # run + print, no write
    uv run python -m eval.eval_bird_minidev --limit 10  # tiny subset (wiring check)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date

from dotenv import load_dotenv

from eval.datasets.bird import loader
from eval.datasets.bird.slice_minidev import SLICE_FILE, load_minidev_slice_ids
from eval.eval_bird import RESULTS_PATH, _git_commit, append_results, build_bird_cases
from eval.eval_bird_rag import make_rag_run_one
from eval.harness import batch_session_id, run_batch
from eval.metrics import BatchReport, summary_lines
from eval.model_select import model_id
from nl2sql import obs
from nl2sql.prompts import PROMPT_VERSION


def slice_minidev_id() -> str:
    return json.loads(SLICE_FILE.read_text())["_meta"]["slice"]


def results_row(
    report: BatchReport, *, model: str, prompt_version: str, commit: str
) -> str:
    """Format the RESULTS.md log row (CLAUDE.md §6 — full config). No numbered
    Step owns this slice, so the Step column records the slice name instead of
    fabricating a step number."""
    number = f"{report.pass_at_1:.3f} ({report.n_correct}/{report.total})"
    return (
        f"| {date.today().isoformat()} | minidev | pass@1 (schema-RAG) | {number} | "
        f"{model} | {slice_minidev_id()} | {prompt_version} | {commit} |"
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ids = load_minidev_slice_ids()
    if limit is not None:
        ids = ids[:limit]
    cases, evidence = build_bird_cases(ids, questions=loader.load_minidev_questions())

    model = model_id()
    print(f"scoring {len(cases)} Mini-Dev questions (schema-RAG) on `{model}`…")
    report = run_batch(
        cases,
        make_rag_run_one(evidence),
        session_id=batch_session_id(
            "bird-minidev-rag", model=model, prompt_version=PROMPT_VERSION
        ),
    )
    print("\n" + "\n".join(summary_lines(report)))

    row = results_row(
        report, model=model, prompt_version=PROMPT_VERSION, commit=_git_commit()
    )
    print("\nRESULTS.md row:\n" + row)
    if write and limit is None:
        append_results(row)
        print(f"\nappended to {RESULTS_PATH.name}")
    elif limit is not None:
        print("\n(--limit run: not writing RESULTS.md)")
    # Short-lived job: export buffered Langfuse spans before exit. A no-op offline
    # and redundant with the SDK's atexit flush, but makes export deterministic.
    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
