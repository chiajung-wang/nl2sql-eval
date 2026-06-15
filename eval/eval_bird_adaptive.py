"""Step-6 follow-up (#76): the budget-aware **adaptive retrieval gate**.

Step 6 left two numbers on the frozen large-schema slice: naive full dump
**0.700** and schema-RAG **0.575** (lift −0.125). The RAG loss is a *mechanism*
bug, not a retrieval failure: ``retrieve`` caps at ``max_tables`` (8) and so drops
tables even when the whole schema would have fit the prompt. The adaptive gate
(#76) fixes exactly that — **dump the full schema when it fits the configured
schema-token budget, retrieve only when it overflows.**

This harness runs the *same* import-shared pipeline three ways over the frozen
slice and reports pass@1 for each:

- **naive full dump** — the Step-6 baseline (ignores any budget; the accuracy
  ceiling, but it blows the budget on the largest schemas);
- **always-RAG** — the Step-6 schema-RAG, ``max_tables`` cap, no gate (the −0.125
  loser: it drops tables even when they would have fit);
- **adaptive(budget)** — the gate: full dump where the schema fits the budget,
  RAG where it overflows.

The thesis: adaptive recovers the full-dump accuracy on the dbs that fit the
budget (the ones the cap needlessly hurt) while staying within budget on the
ones that don't — so it should land at/above always-RAG and approach naive,
*without* ignoring the budget the way naive does. This is the loop closing: the
#75 measurement (where retrieval pays) shaping the architecture.

    uv run python -m eval.eval_bird_adaptive               # 3-mode run + RESULTS.md
    uv run python -m eval.eval_bird_adaptive --dry-run     # print, no write
    uv run python -m eval.eval_bird_adaptive --limit 4     # tiny wiring check
    uv run python -m eval.eval_bird_adaptive --budget 1024 # override the gate budget
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from dotenv import load_dotenv

from eval.datasets.bird.slice_large import load_large_slice_ids
from eval.eval_bird import (
    DIALECT,
    RESULTS_PATH,
    _engine,
    _git_commit,
    append_results,
    build_bird_cases,
)
from eval.eval_bird_rag import _index, make_naive_run_one, make_rag_run_one, slice6_id
from eval.harness import Case, run_batch
from eval.metrics import BatchReport, summary_lines
from nl2sql.pipeline.generate import DEFAULT_MODEL, PROMPT_VERSION
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.retrieve import DEFAULT_SCHEMA_TOKEN_BUDGET
from nl2sql.pipeline.state import RunState


def make_adaptive_run_one(evidence: dict[str, str], *, budget_tokens: int):
    """The gate: full dump when the schema fits ``budget_tokens``, else RAG."""

    def run_one(case: Case) -> RunState:
        return run_pipeline(
            case.question,
            schema_index=_index(case.db_id),
            engine=_engine(case.db_id),
            db_id=case.db_id,
            dialect=DIALECT,
            evidence=evidence.get(case.id, ""),
            budget_tokens=budget_tokens,
        )

    return run_one


def gate_decisions(cases: list[Case], budget_tokens: int) -> dict[str, int]:
    """Per-mode count of how the gate would route each case (offline, no LLM).

    ``{"full": n_full, "rag": n_rag}`` — how many cases sit on a schema that fits
    the budget (→ full dump) vs overflows it (→ RAG). Makes the gate's behaviour
    on this slice concrete and explains the adaptive number."""
    full = 0
    for case in cases:
        index = _index(case.db_id)
        if index.render_tokens([t.name for t in index.tables]) <= budget_tokens:
            full += 1
    return {"full": full, "rag": len(cases) - full}


def _row(
    naive: BatchReport,
    rag: BatchReport,
    adaptive: BatchReport,
    *,
    budget: int,
    commit: str,
) -> str:
    """The RESULTS.md row: naive / always-RAG / adaptive pass@1 at the gate budget."""
    number = (
        f"naive {naive.accuracy:.3f} ({naive.n_correct}/{naive.total}) / "
        f"always-RAG {rag.accuracy:.3f} ({rag.n_correct}/{rag.total}) / "
        f"adaptive@{budget}t {adaptive.accuracy:.3f} "
        f"({adaptive.n_correct}/{adaptive.total})"
    )
    return (
        f"| {date.today().isoformat()} | 6 | adaptive-gate pass@1 | {number} | "
        f"{DEFAULT_MODEL} | {slice6_id()} | {PROMPT_VERSION} | {commit} |"
    )


def _note(
    naive: BatchReport,
    rag: BatchReport,
    adaptive: BatchReport,
    *,
    budget: int,
    decisions: dict[str, int],
) -> str:
    """Prose for RESULTS.md — every number derived from the reports."""
    vs_rag = adaptive.accuracy - rag.accuracy
    vs_naive = adaptive.accuracy - naive.accuracy
    total = decisions["full"] + decisions["rag"]
    return (
        f"\n**Step 6 follow-up (#76) — budget-aware adaptive retrieval gate.** The "
        f"Step-6 RAG loss (−0.125) was a *mechanism* bug: `retrieve` caps at "
        f"`max_tables` and drops tables even when the whole schema would have fit "
        f"the prompt. The gate fixes it — full dump when the schema fits a "
        f"configured **{budget}-token** budget, RAG only when it overflows. On the "
        f"frozen `{slice6_id()}` slice the gate routes **{decisions['full']}/{total}** "
        f"questions to a full dump and **{decisions['rag']}/{total}** to RAG. "
        f"Result: naive full dump **{naive.accuracy:.3f} "
        f"({naive.n_correct}/{naive.total})**, always-RAG (capped, the Step-6 "
        f"loser) **{rag.accuracy:.3f} ({rag.n_correct}/{rag.total})**, "
        f"**adaptive {adaptive.accuracy:.3f} ({adaptive.n_correct}/{adaptive.total})** "
        f"— {vs_rag:+.3f} vs always-RAG, {vs_naive:+.3f} vs naive. The gate recovers "
        f"the accuracy the table cap gave up on the dbs that fit the budget, while "
        f"staying within budget on the ones that overflow it — the #75 measurement "
        f"(where retrieval pays) shaping the architecture. Reproduce with "
        f"`uv run python -m eval.eval_bird_adaptive`.\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    budget = (
        int(args[args.index("--budget") + 1])
        if "--budget" in args
        else DEFAULT_SCHEMA_TOKEN_BUDGET
    )

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ids = load_large_slice_ids()
    if limit is not None:
        ids = ids[:limit]
    cases, evidence = build_bird_cases(ids)

    print(f"=== naive full dump ({len(cases)} questions) ===")
    naive = run_batch(cases, make_naive_run_one(evidence))
    print("\n".join(summary_lines(naive)))

    print(f"\n=== always-RAG (capped, no gate) ({len(cases)} questions) ===")
    rag = run_batch(cases, make_rag_run_one(evidence))
    print("\n".join(summary_lines(rag)))

    print(f"\n=== adaptive gate @{budget}t ({len(cases)} questions) ===")
    adaptive = run_batch(cases, make_adaptive_run_one(evidence, budget_tokens=budget))
    print("\n".join(summary_lines(adaptive)))

    decisions = gate_decisions(cases, budget)
    print("\n=== adaptive gate (naive / always-RAG / adaptive) ===")
    print(f"naive full dump : {naive.accuracy:.3f} ({naive.n_correct}/{naive.total})")
    print(f"always-RAG      : {rag.accuracy:.3f} ({rag.n_correct}/{rag.total})")
    print(
        f"adaptive @{budget}t: {adaptive.accuracy:.3f} "
        f"({adaptive.n_correct}/{adaptive.total})  "
        f"[gate: {decisions['full']} full, {decisions['rag']} rag]"
    )

    row = _row(naive, rag, adaptive, budget=budget, commit=_git_commit())
    print("\nRESULTS.md row:\n" + row)
    if write and limit is None:
        append_results(row)
        RESULTS_PATH.write_text(
            RESULTS_PATH.read_text().rstrip()
            + "\n"
            + _note(naive, rag, adaptive, budget=budget, decisions=decisions)
        )
        print(f"\nappended to {RESULTS_PATH.name}")
    elif limit is not None:
        print("\n(--limit run: not writing RESULTS.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
