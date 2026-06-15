# Issue 2 — Budget-aware adaptive retrieval gate

**Type:** AFK
**Phase:** Step 6 follow-up — *the loop closing (measurement → architecture)*

## Parent

`docs/plans/step-6-follow-up/plan-step-6-follow-up.md`

## What to build

Today `retrieve()` **always** narrows to `DEFAULT_MAX_TABLES = 8`
(`src/nl2sql/schema_index/__init__.py:39`), so on a db that already fits the
budget it can only drop a needed table — the −0.125 mechanism. Make retrieval
**adaptive**: dump the full schema when it fits a **configured schema-token
budget** (a cost/latency policy, *not* the model's context limit — BIRD always
fits that); fall back to RAG selection only when the full schema exceeds the
budget. This is the design the #49 finding implies, and it makes the harness
demonstrably load-bearing — a measured result shaping the system, not just
grading it.

- Add a budget-aware decision in the retrieve stage: if the *full* rendered
  schema is within the configured schema-token budget (calibrated to the issue-1
  crossover), render the full dump and record the decision on the state
  (`retrieval_mode = "full" | "rag"`); else run the existing top-`max_tables`
  selection.
- Keep it **deterministic** and config-driven — no LLM call to decide (CLAUDE.md
  §4/§7). The threshold is an explicit config key, not a magic number inline.
- Preserve import-sharing: the demo and the harness must hit the **same** gate
  (CLAUDE.md §3). The loop-aware `floor` re-trigger (#46) still applies on top in
  RAG mode.
- Surface the decision on the span (`retrieval_mode`, budget, n_tables) so a
  trace shows *why* it chose full vs RAG — no result rows, schema metadata only.

## Measurement

- Run the harness in three modes over the issue-1 crossover slice (spans both
  regimes): **naive (budgeted truncation)**, **always-RAG**, **adaptive**.
- Append a `RESULTS.md` row showing adaptive ≥ max(naive, always-RAG) within each
  regime — i.e. adaptive avoids the under-budget loss *and* keeps the over-budget
  win. State the crossover threshold the gate uses.

## Acceptance criteria

- [ ] Adaptive gate in `retrieve.py` (or a thin helper it calls): full dump when
      schema fits budget, RAG selection on overflow; deterministic, config-driven
- [ ] `retrieval_mode` recorded on state + span; demo and harness share the gate
- [ ] Three-mode comparison (naive / always-RAG / adaptive) in `RESULTS.md` with
      full config, showing adaptive does not regress either regime
- [ ] Unit test for the gate's threshold decision (fits → full, overflows → rag)
- [ ] `uv run pytest` green; lint/format clean; module boundaries intact

## Notes

- This is the interview headline: "I measured that RAG costs accuracy below a
  schema-token budget and pays above it, so the system retrieves adaptively — the
  harness shaped the architecture." The honest framing: with 200K-token context
  windows the budget is a *cost/latency policy*, not a hard limit, and on BIRD
  the gate almost always picks `full` — a **no-regret guard** that removes the
  −0.125 loss while keeping the over-budget win.
- Budget estimate can stay heuristic (a cheap token estimate of the rendered
  schema) — consistent with the heuristic-first stance (PRD §5).

## Outcome (shipped — 2026-06-15)

Done, merged. The gate (`schema_fits_budget` → full dump when the schema fits the
budget, RAG when it overflows) is deterministic, config-driven
(`DEFAULT_SCHEMA_TOKEN_BUDGET = 2048`), records `retrieval_mode` on state + span,
and is import-shared via `run_pipeline` (`budget_tokens=None` keeps the prior
always-RAG). Three-mode run: naive full dump **0.675** / always-RAG (capped)
**0.650** / adaptive@2048t **0.675** (gate routed 24/40 full, 16/40 RAG).

The expected "adaptive ≥ max(naive, always-RAG)" held this run, **but** the deltas
(+0.025 vs always-RAG, +0.000 vs naive) sit **within the ~0.05 sampling-noise
floor** from #75, and the Step-6 −0.125 loss did **not** reproduce. So the honest
claim is **structural / no-regret** — a deterministic per-db full-vs-RAG choice
that never pays the table-cap's drop risk where the schema fits — not a measured
accuracy lift. Reproduce: `uv run python -m eval.eval_bird_adaptive`. Walkthrough
in `issue-76-summary.html`.

## Tracking

**GitHub:** [#76](https://github.com/chiajung-wang/nl2sql-eval/issues/76) · label `agent-ready`, `step-6`

**PR:** [#78](https://github.com/chiajung-wang/nl2sql-eval/pull/78) (merged)

**Blocked by:** [#75](https://github.com/chiajung-wang/nl2sql-eval/issues/75) (needs the crossover budget to calibrate the gate threshold).
