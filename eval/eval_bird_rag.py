"""Step 6 Definition of Done: the naive-dump → schema-RAG **retrieval lift**.

Runs the frozen **large-schema** Step-6 slice through the *same* import-shared
pipeline twice — once with the Step-3 naive full-schema dump, once with
schema-RAG (the ``retrieve`` stage selects the relevant tables) — and reports the
**lift** in pass@1 accuracy, plus **retrieval recall** (how well the retriever
covered the gold query's tables). Large-schema dbs are exactly where dumping the
whole schema overflows the prompt, so this is where retrieval earns its keep.

This is the second of the project's two sharpest findings (the first was Step 5's
pass@1→pass@k gap). The lift and recall are appended to ``RESULTS.md`` with full
config (CLAUDE.md §6).

    uv run python -m eval.eval_bird_rag             # run + append RESULTS.md
    uv run python -m eval.eval_bird_rag --dry-run   # run + print, no RESULTS.md write
    uv run python -m eval.eval_bird_rag --limit 4   # tiny subset (wiring check)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from functools import cache

from dotenv import load_dotenv

from eval.datasets.bird.slice_large import SLICE_FILE, load_large_slice_ids
from eval.eval_bird import (
    DIALECT,
    RESULTS_PATH,
    _engine,
    _git_commit,
    _schema,
    append_results,
    build_bird_cases,
)
from eval.harness import Case, batch_session_id, run_batch
from eval.metrics import BatchReport, summary_lines
from eval.model_select import model_id
from nl2sql import obs
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState
from nl2sql.profiling import resolve_column_descriptions
from nl2sql.prompts import PROMPT_VERSION
from nl2sql.schema_index import build_schema_index


@cache
def _index(db_id: str):
    """The db's schema index (cached) — built once, reused across its questions.

    The field-description source is the ``METADATA_SOURCE`` axis (#140): with the
    default ``supplied`` (or no ``profiles/<db>.json`` artifact) this resolves to an
    empty map, so the index is byte-identical to before; ``profiling``/``fused``
    ride the cached data-derived descriptions into the rendered schema the generator
    sees. This is the one call site that makes the selector active in a real run.
    """
    return build_schema_index(
        _engine(db_id),
        column_descriptions=resolve_column_descriptions(db_id),
    )


def slice6_id() -> str:
    return json.loads(SLICE_FILE.read_text())["_meta"]["slice"]


def make_naive_run_one(evidence: dict[str, str]):
    """Step-3 baseline: the whole schema dumped into the prompt (no retrieval)."""

    def run_one(case: Case) -> RunState:
        return run_pipeline(
            case.question,
            schema=_schema(case.db_id),
            engine=_engine(case.db_id),
            db_id=case.db_id,
            dialect=DIALECT,
            evidence=evidence.get(case.id, ""),
            model=model_id(),
        )

    return run_one


def make_rag_run_one(evidence: dict[str, str]):
    """Schema-RAG: ``retrieve`` selects the relevant tables for this question."""

    def run_one(case: Case) -> RunState:
        return run_pipeline(
            case.question,
            schema_index=_index(case.db_id),
            engine=_engine(case.db_id),
            db_id=case.db_id,
            dialect=DIALECT,
            evidence=evidence.get(case.id, ""),
            model=model_id(),
        )

    return run_one


def lift_row(
    naive: BatchReport,
    rag: BatchReport,
    *,
    model: str,
    prompt_version: str,
    commit: str,
) -> str:
    """Format the RESULTS.md row: naive-baseline → retrieval accuracy + the lift."""
    lift = rag.accuracy - naive.accuracy
    number = (
        f"{naive.accuracy:.3f} ({naive.n_correct}/{naive.total}) → "
        f"{rag.accuracy:.3f} ({rag.n_correct}/{rag.total}) [lift {lift:+.3f}]"
    )
    return (
        f"| {date.today().isoformat()} | 6 | retrieval lift (pass@1) | {number} | "
        f"{model} | {slice6_id()} | {prompt_version} | {commit} |"
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

    ids = load_large_slice_ids()
    if limit is not None:
        ids = ids[:limit]
    cases, evidence = build_bird_cases(ids)

    print(f"=== naive full-schema dump ({len(cases)} large-schema questions) ===")
    naive = run_batch(
        cases,
        make_naive_run_one(evidence),
        session_id=batch_session_id(
            "bird-rag-naive", model=model_id(), prompt_version=PROMPT_VERSION
        ),
    )
    print("\n".join(summary_lines(naive)))

    print(f"\n=== schema-RAG ({len(cases)} questions) ===")
    rag = run_batch(
        cases,
        make_rag_run_one(evidence),
        session_id=batch_session_id(
            "bird-rag-select", model=model_id(), prompt_version=PROMPT_VERSION
        ),
    )
    print("\n".join(summary_lines(rag)))

    lift = rag.accuracy - naive.accuracy
    recall = rag.mean_retrieval_recall
    print("\n=== retrieval lift ===")
    print(f"naive pass@1: {naive.accuracy:.3f} ({naive.n_correct}/{naive.total})")
    print(f"RAG   pass@1: {rag.accuracy:.3f} ({rag.n_correct}/{rag.total})")
    print(f"lift:         {lift:+.3f}")
    if recall is not None:
        print(f"retrieval recall (RAG): {recall:.3f} (over {rag.n_with_recall} cases)")

    row = lift_row(
        naive,
        rag,
        model=model_id(),
        prompt_version=PROMPT_VERSION,
        commit=_git_commit(),
    )
    print("\nRESULTS.md row:\n" + row)
    if write and limit is None:
        append_results(row)
        if recall is not None:
            _append_recall_note(naive, rag, recall)
        print(f"\nappended to {RESULTS_PATH.name}")
    elif limit is not None:
        print("\n(--limit run: not writing RESULTS.md)")
    # Short-lived job: export buffered Langfuse spans before exit. A no-op offline
    # and redundant with the SDK's atexit flush, but makes export deterministic.
    obs.flush()
    return 0


def _append_recall_note(naive: BatchReport, rag: BatchReport, recall: float) -> None:
    """Append the prose note that accompanies the Step-6 lift row in RESULTS.md.

    Sign-aware and honest: retrieval's benefit is *conditional* on the schema not
    fitting the prompt. The note reads the measured lift and frames it from the
    data, never from a hoped-for headline."""
    lift = rag.accuracy - naive.accuracy
    missed = 1.0 - recall
    if lift < 0:
        reading = (
            f"On these dbs (≤14 tables) the whole schema still **fits** the "
            f"model's context, so the naive dump already hands it every table, "
            f"while schema-RAG — whose job is to *drop* tables to fit a budget — "
            f"occasionally drops a **needed** one. Recall **{recall:.3f}** means "
            f"~{missed:.1%} of the gold tables were missed, and those become wrong "
            f"answers: the recall metric diagnoses the loss directly. Retrieval is "
            f"**not free** — its lift is where the schema *overflows*; here it does "
            f"not, so retrieval can only lose information. This is the twin of "
            f"Step 5's finding: measurement over a hoped-for headline."
        )
    else:
        reading = (
            f"Schema-RAG paid off: surfacing only the relevant tables helped where "
            f"the full dump would distract or overflow. Recall **{recall:.3f}** "
            f"({rag.n_with_recall} cases) shows how well the retriever covered the "
            f"gold tables — recall is reported alongside accuracy because the "
            f"silent wrong-schema failure (valid SQL, wrong tables, no error) is "
            f"invisible to accuracy alone."
        )
    note = (
        f"\n**Step 6 — naive-dump → schema-RAG retrieval lift (large-schema slice).** "
        f"On the frozen `{slice6_id()}` slice, schema-RAG moves pass@1 from "
        f"**{naive.accuracy:.3f} ({naive.n_correct}/{naive.total})** to "
        f"**{rag.accuracy:.3f} ({rag.n_correct}/{rag.total})** — a lift of "
        f"**{lift:+.3f}** — with retrieval recall **{recall:.3f}**. {reading} "
        f"Reproduce with `uv run python -m eval.eval_bird_rag`.\n"
    )
    RESULTS_PATH.write_text(RESULTS_PATH.read_text().rstrip() + "\n" + note)


if __name__ == "__main__":
    raise SystemExit(main())
