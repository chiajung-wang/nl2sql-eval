# Issue 1 — Controlled budget experiment + retrieval crossover threshold

**Type:** AFK
**Phase:** Step 6 follow-up — *find the crossover where retrieval starts to pay*

## Parent

`docs/plans/step-6-follow-up/plan-step-6-follow-up.md`

## Context (why this isn't an "overflow slice")

Step 6 (#49) reported retrieval lift **−0.125** because schema-RAG can only
*drop* tables, and on BIRD every db's full schema fits the context. We checked:
the **largest BIRD dev schema is `formula_1` (13 tables) / `european_football_2`
(~7.3K chars ≈ ~1.8K tokens)** — both fit a 200K-token window trivially. So there
is **no BIRD db where the full schema cannot fit** and retrieval is *forced*. The
"RAG fits what the dump can't" regime is **not naturally demonstrable on BIRD**,
and we are **not** pretending otherwise (no large-dataset detour — that's Step
10's BigQuery reach).

Instead we demonstrate the *mechanism* honestly under a **configured schema-token
budget** — a real cost/latency policy a production system imposes — and locate the
**crossover**: below the budget the full dump wins; above it, RAG-select beats
naive truncation. This is labeled as a controlled experiment, not a claim of
natural overflow.

## What to build

- **Frozen slice spanning both regimes.** A seeded, stratified, checked-in ID
  list under `eval/datasets/bird/` (e.g. `step6fu-budget-crossover`) mixing
  small-fit dbs and the largest BIRD dev dbs (`formula_1`,
  `european_football_2`, `codebase_community`). Document per-db table counts and
  rendered-schema token estimates so the regimes are concrete.
- **Two retrieval modes under a configured schema-token budget:**
  - **naive-truncate-to-budget** — fill the budget in declaration order (the
    "dumb" baseline a fixed budget forces on a non-retrieving system);
  - **RAG-select-to-budget** — fill the same budget with the most-relevant tables.
- **Sweep the budget** across a small set of values and record, per budget:
  accuracy for both modes, retrieval recall, pass@1/pass@k. Identify the
  **crossover budget** where RAG-select overtakes truncation.
- Append `RESULTS.md` rows with full config (model, slice ID, prompt version,
  date, commit). State the crossover explicitly and label the experiment as a
  controlled mechanism/threshold demo (BIRD never overflows context naturally).

## Acceptance criteria

- [ ] Crossover slice frozen, seeded, stratified, checked-in as explicit ID list;
      per-db table counts + token estimates documented
- [ ] naive-truncate-to-budget vs RAG-select-to-budget measured across a budget
      sweep; accuracy + recall + pass@1/pass@k recorded
- [ ] Crossover budget identified and stated (below → dump wins, above → RAG wins)
- [ ] `RESULTS.md` rows record the sweep with full config, labeled as a
      controlled experiment (no natural-overflow claim)
- [ ] `uv run pytest` green; lint/format clean

## Notes

- The naive-truncate-to-budget mode is new (the Step-3/6 naive baseline sent the
  *whole* schema because it fit). It's a thin variant of the existing render path
  — truncate by the same budget, no new pipeline stage.
- Comparator and guardrails untouched; this issue adds a slice + a budgeted
  render variant + measured rows.
- The crossover budget calibrates the adaptive gate in issue 2.

## Outcome (shipped — 2026-06-15)

Done, merged. RAG-select beats naive-truncation at every swept budget (gap
+0.025–+0.100, peak @512t), recall climbs **0.450→1.000** — **but** the modes
converge at **4096t** (selection divergence 0; identical prompts) where they still
differ by +0.050, a **sampling-noise floor**. So the pass@1 gaps are suggestive,
not conclusive on 40 questions; **recall is the robust signal**. Convergence is
defined on selection divergence, not the accuracy gap. Reproduce:
`uv run python -m eval.eval_bird_budget`. Full table + note in `RESULTS.md`;
walkthrough in `issue-75-summary.html`.

> AC note: `pass@k` was **not** recorded — the experiment uses the single-shot
> `schema=` path deliberately, to isolate the budget variable from self-correction.

## Tracking

**GitHub:** [#75](https://github.com/chiajung-wang/nl2sql-eval/issues/75) · label `agent-ready`, `step-6`

**PR:** [#77](https://github.com/chiajung-wang/nl2sql-eval/pull/77) (merged)

**Blocks:** [#76](https://github.com/chiajung-wang/nl2sql-eval/issues/76) (adaptive gate — calibrated by this crossover)

**Blocked by:** none (the retrieve stage, recall metric, and rag eval entry all
landed in Step 6: #45–#49).
