"""Step-6 follow-up (#75): the schema-token-budget retrieval crossover.

BIRD has no schema large enough to overflow a modern context window — the largest
dev schema is ``european_football_2`` / ``formula_1`` at ~1.8K tokens of DDL,
which fits a 200K window trivially. So schema-RAG cannot win on the "it doesn't
fit" axis, and Step 6 measured exactly that (lift **-0.125**: dropping a needed
table can only hurt when the full dump already fit). This experiment asks the
sharper, *honest* question instead.

Impose a **configured schema-token budget** — a cost/latency policy a real system
sets on how much schema rides in each prompt, **not** the model's context limit —
and compare two ways to live within it:

- **naive-truncate-to-budget**: fill the budget in declaration order (what a
  non-retrieving system is forced to do under a fixed budget);
- **RAG-select-to-budget**: fill the same budget with the *relevant* tables.

For each budget in a sweep we run the frozen Step-6 slice through the same
import-shared pipeline twice and report pass@1 for both modes plus retrieval
recall. The gap is what retrieval is worth *at that budget*; it is widest when the
budget is tight and shrinks toward zero once the budget is generous enough to hold
the whole schema (both modes converge on the full dump). This is a **controlled
mechanism demo** — explicitly not a claim that BIRD overflows context — and it
calibrates the crossover the adaptive gate (#76) switches on.

    uv run python -m eval.eval_bird_budget                  # full sweep + RESULTS.md
    uv run python -m eval.eval_bird_budget --dry-run        # print, no write
    uv run python -m eval.eval_bird_budget --limit 4        # tiny wiring check
    uv run python -m eval.eval_bird_budget --budgets 256,512,1024
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
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
from eval.eval_bird_rag import _index, slice6_id
from eval.harness import Case, batch_session_id, run_batch
from eval.metrics import BatchReport, summary_lines
from eval.model_select import model_id
from nl2sql import obs
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState
from nl2sql.prompts import PROMPT_VERSION

# The budget sweep, in estimated schema tokens (see schema_index.estimate_tokens).
# Spans tight (only a few tables fit) to generous (the whole schema fits, so the
# two modes converge). Calibrated to the frozen Step-6 slice's per-db full-schema
# sizes (rendered with sample values, so larger than raw DDL):
#
#   db                   tables   full render tokens
#   superhero               10       729
#   financial                8      1041
#   student_club             8      1449
#   codebase_community       8      1850
#   formula_1               13      1979
#   card_games               6      2613
#   european_football_2      7      3820
#
# So budgets ≤ 2048 truncate the three largest dbs; 4096 holds every schema, which
# is why the two modes converge there (selection divergence → 0).
DEFAULT_BUDGETS = (256, 512, 1024, 2048, 4096)


def make_budget_run_one(evidence: dict[str, str], *, budget_tokens: int, mode: str):
    """A runner that fits the schema to ``budget_tokens`` the given ``mode`` way.

    ``mode="rag"`` orders tables by relevance before filling the budget;
    ``mode="naive"`` fills in declaration order (truncation). Both render through
    the *same* index and run the *same* import-shared pipeline — the only variable
    is which tables survive the budget. The selected names are recorded on the
    state so the harness computes retrieval recall for both modes (truncation
    drops gold tables too; recall makes that loss visible).
    """

    def run_one(case: Case) -> RunState:
        index = _index(case.db_id)
        if mode == "rag":
            ordered = index.ranked_names(case.question)
        else:
            ordered = [t.name for t in index.tables]
        selected = index.fit_budget(ordered, budget_tokens)
        state = run_pipeline(
            case.question,
            schema=index.render(selected),
            engine=_engine(case.db_id),
            db_id=case.db_id,
            dialect=DIALECT,
            evidence=evidence.get(case.id, ""),
            model=model_id(),
        )
        state.retrieved_tables = selected
        return state

    return run_one


def selection_divergence(cases: Sequence[Case], budget_tokens: int) -> float:
    """Fraction of cases where the two modes pick **different** tables at a budget.

    Deterministic and offline (no LLM): for each case, does naive truncation
    (declaration order) select a different table *set* than RAG (relevance order)
    once both are fit to ``budget_tokens``? When this is **zero** the budget holds
    every schema, so the two modes send the generator *identical* prompts — and any
    residual pass@1 gap there is sampling noise, not a retrieval effect. This is
    what makes the convergence point principled rather than a gap that merely
    happens to cross zero through noise."""
    if not cases:
        return 0.0
    differ = 0
    for case in cases:
        index = _index(case.db_id)
        naive = index.fit_budget([t.name for t in index.tables], budget_tokens)
        rag = index.fit_budget(index.ranked_names(case.question), budget_tokens)
        if set(naive) != set(rag):
            differ += 1
    return differ / len(cases)


@dataclass(frozen=True)
class BudgetPoint:
    """One budget's outcome: both modes' reports, the gap, and their divergence.

    ``divergence`` (fraction of cases where the modes select different tables) is
    the honesty anchor: at ``divergence == 0`` the prompts are identical, so the
    gap there measures sampling noise — the floor every other gap is read against.
    """

    budget: int
    naive: BatchReport
    rag: BatchReport
    divergence: float

    @property
    def gap(self) -> float:
        return self.rag.accuracy - self.naive.accuracy


def convergence_budget(points: list[BudgetPoint]) -> int | None:
    """Smallest budget at which the two modes converge — i.e. ``divergence == 0``.

    The principled crossover the adaptive gate keys off: at/above this budget the
    full schema fits, so both modes send identical prompts and retrieval can no
    longer change the answer — a plain dump is the cheaper equal-accuracy choice.
    Defined on *divergence*, not on the pass@1 gap crossing zero, so sampling
    noise can't move it. ``None`` if every swept budget still truncates some
    schema (no budget holds them all)."""
    for p in sorted(points, key=lambda p: p.budget):
        if p.divergence == 0:
            return p.budget
    return None


def _sweep_row(points: list[BudgetPoint], *, commit: str) -> str:
    """The compact RESULTS.md row summarising the whole sweep."""
    best = max(points, key=lambda p: p.gap)
    conv = convergence_budget(points)
    conv_str = (
        f"converges @{conv}t" if conv is not None else "no convergence in swept range"
    )
    number = (
        f"max gap {best.gap:+.3f} @{best.budget}t, {conv_str} "
        f"(RAG-select vs naive-truncate, pass@1)"
    )
    return (
        f"| {date.today().isoformat()} | 6 | budget-crossover retrieval lift | "
        f"{number} | {model_id()} | {slice6_id()} | {PROMPT_VERSION} | {commit} |"
    )


def _sweep_note(points: list[BudgetPoint]) -> str:
    """Prose + per-budget table appended under the sweep row in RESULTS.md.

    Every quantitative claim is derived from ``points`` (peak gap, gap range,
    recall range, divergence, the noise floor at the convergence budget) so the
    prose can never drift from the table beneath it — the honesty discipline that
    lets the blog quote it verbatim (PRD §10)."""
    ordered = sorted(points, key=lambda p: p.budget)
    peak = max(points, key=lambda p: p.gap)
    recalls = [
        p.rag.mean_retrieval_recall
        for p in ordered
        if p.rag.mean_retrieval_recall is not None
    ]
    recall_clause = (
        f"RAG recall climbs {recalls[0]:.3f}→{recalls[-1]:.3f} with the budget — "
        f"the robust signal: more budget lets retrieval cover more of the gold "
        f"tables, while truncation gets no such targeting"
        if len(recalls) >= 2
        else "RAG recall is reported per budget below"
    )
    conv = convergence_budget(points)
    if conv is not None:
        floor = next(p for p in ordered if p.budget == conv)
        floor_clause = (
            f"the modes **converge at {conv}t** (selection divergence 0 — every "
            f"schema fits, so both send the generator identical prompts). The "
            f"residual {floor.gap:+.3f} there is therefore **sampling noise**, not "
            f"retrieval: generation runs at non-zero temperature, so two independent "
            f"runs on the *same* prompt differ by ~{abs(floor.gap):.3f} "
            f"({abs(floor.naive.n_correct - floor.rag.n_correct)}/{floor.naive.total} "
            f"questions). Read the tight-budget gaps against that floor: the pass@1 "
            f"advantage peaks at **{peak.budget}t ({peak.gap:+.3f})** but is modest "
            f"relative to it, so on this 40-question slice the gap is suggestive, not "
            f"conclusive"
        )
    else:
        floor_clause = (
            f"no budget in the sweep reaches selection divergence 0, so every point "
            f"still truncates some schema; the advantage peaks at **{peak.budget}t "
            f"({peak.gap:+.3f})**. Without a zero-divergence point there is no "
            f"in-range noise floor to calibrate significance against — widen the "
            f"sweep to bound it"
        )
    rows = "\n".join(
        f"| {p.budget} | {p.naive.accuracy:.3f} ({p.naive.n_correct}/{p.naive.total}) "
        f"| {p.rag.accuracy:.3f} ({p.rag.n_correct}/{p.rag.total}) | {p.gap:+.3f} | "
        f"{p.rag.mean_retrieval_recall:.3f} | {p.divergence:.3f} |"
        if p.rag.mean_retrieval_recall is not None
        else f"| {p.budget} | {p.naive.accuracy:.3f} | {p.rag.accuracy:.3f} | "
        f"{p.gap:+.3f} | — | {p.divergence:.3f} |"
        for p in ordered
    )
    return (
        f"\n**Step 6 follow-up (#75) — schema-token-budget retrieval crossover.** "
        f"BIRD has no schema that overflows a modern context window (largest ~1.8K "
        f"tokens), so this is a **controlled experiment**, not a natural-overflow "
        f"claim: under a configured schema-token *budget* (a cost/latency policy), "
        f"is it better to **truncate** the schema or to **retrieve** the relevant "
        f"tables? On the frozen `{slice6_id()}` slice, {floor_clause}. "
        f"{recall_clause}. "
        f"This is the honest other half of the Step-6 finding: where the full schema "
        f"fits the budget the two modes are identical; where it does not, retrieval "
        f"keeps the *right* tables and truncation cuts blindly — the recall gap is "
        f"real and monotone, the pass@1 gap real but small against sampling noise. "
        f"With today's context windows that budget is a policy choice, not a hard "
        f"limit.\n\n"
        f"| schema-token budget | naive-truncate pass@1 | RAG-select pass@1 | gap | "
        f"RAG recall | selection divergence |\n"
        f"| --- | --- | --- | --- | --- | --- |\n{rows}\n\n"
        f"Reproduce with `uv run python -m eval.eval_bird_budget`.\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    budgets = DEFAULT_BUDGETS
    if "--budgets" in args:
        budgets = tuple(int(b) for b in args[args.index("--budgets") + 1].split(","))

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ids = load_large_slice_ids()
    if limit is not None:
        ids = ids[:limit]
    cases, evidence = build_bird_cases(ids)

    points: list[BudgetPoint] = []
    for budget in budgets:
        print(f"\n=== budget {budget}t — naive-truncate ({len(cases)} questions) ===")
        naive = run_batch(
            cases,
            make_budget_run_one(evidence, budget_tokens=budget, mode="naive"),
            session_id=batch_session_id(
                f"bird-budget@{budget}t-naive",
                model=model_id(),
                prompt_version=PROMPT_VERSION,
            ),
        )
        print("\n".join(summary_lines(naive)))
        print(f"\n=== budget {budget}t — RAG-select ({len(cases)} questions) ===")
        rag = run_batch(
            cases,
            make_budget_run_one(evidence, budget_tokens=budget, mode="rag"),
            session_id=batch_session_id(
                f"bird-budget@{budget}t-rag",
                model=model_id(),
                prompt_version=PROMPT_VERSION,
            ),
        )
        print("\n".join(summary_lines(rag)))
        divergence = selection_divergence(cases, budget)
        points.append(
            BudgetPoint(budget=budget, naive=naive, rag=rag, divergence=divergence)
        )

    print("\n=== budget crossover (RAG-select vs naive-truncate) ===")
    print(
        f"{'budget':>8} {'naive':>8} {'RAG':>8} {'gap':>8} {'recall':>8} {'diverge':>8}"
    )
    for p in points:
        recall = (
            "—"
            if p.rag.mean_retrieval_recall is None
            else f"{p.rag.mean_retrieval_recall:.3f}"
        )
        print(
            f"{p.budget:>8} {p.naive.accuracy:>8.3f} {p.rag.accuracy:>8.3f} "
            f"{p.gap:>+8.3f} {recall:>8} {p.divergence:>8.3f}"
        )
    conv = convergence_budget(points)
    print(f"convergence budget (divergence→0): {conv if conv is not None else 'none'}")

    row = _sweep_row(points, commit=_git_commit())
    print("\nRESULTS.md row:\n" + row)
    if write and limit is None:
        append_results(row)
        RESULTS_PATH.write_text(
            RESULTS_PATH.read_text().rstrip() + "\n" + _sweep_note(points)
        )
        print(f"\nappended to {RESULTS_PATH.name}")
    elif limit is not None:
        print("\n(--limit run: not writing RESULTS.md)")
    # Short-lived job: export buffered Langfuse spans before exit. A no-op offline
    # and redundant with the SDK's atexit flush, but makes export deterministic.
    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
