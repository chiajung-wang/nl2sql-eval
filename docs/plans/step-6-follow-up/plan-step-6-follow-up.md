# Plan — Step 6 follow-up: complete the retrieval-lift story (honestly)

**Phase:** Step 6 (Measured features) — *follow-up, pre-blog*

## Status: ✅ complete (2026-06-15)

Both issues landed and merged; the follow-up blog is published. See **Outcome**
at the bottom for the shipped numbers — which differ in emphasis from the
expectations written below: the measured gaps came out *within sampling noise*,
so the honest conclusion is structural (a no-regret gate), not a headline lift.
The pre-result plan text is left intact as the record of intent.

- #75 → PR [#77](https://github.com/chiajung-wang/nl2sql-eval/pull/77) (merged) · `issue-1-budget-crossover-experiment.md`
- #76 → PR [#78](https://github.com/chiajung-wang/nl2sql-eval/pull/78) (merged) · `issue-2-adaptive-retrieval-gate.md`
- blog → PR [#79](https://github.com/chiajung-wang/nl2sql-eval/pull/79) (merged) · `docs/blogs/step-6-follow-up-when-retrieval-pays.md`

## Why this exists

Step 6 (issue #49) reported a retrieval lift of **−0.125** (pass@1 0.700 → 0.575)
with recall **0.942**. The finding is correct and honest, but it only shows the
regime where retrieval **costs** accuracy. The natural question — "where does
retrieval *pay*?" — turns out to have a sharp, current answer.

**The key fact we established:** there is **no BIRD database large enough for
retrieval to help.** The largest dev schema renders to **~3,820 tokens**
(`european_football_2`, with sample values; ~1.8K tokens of raw DDL); `formula_1`
is the most tables at 13 — both fit a 200K-token context window trivially. With modern context windows, schema-RAG's original
reason for existing (2023's 4–8K windows, where you *had* to retrieve) is gone
for anything a public NL→SQL benchmark contains. **That is the finding**, and it
is more senior than a tuned positive lift: it shows judgment about *when a
technique has been obsoleted by the platform*.

So we are **not** chasing a natural positive lift (BIRD can't produce one) and
**not** taking a large-dataset detour (genuinely large schemas belong to Step
10's BigQuery / cloud-warehouse reach). We do three honest things instead:

1. a **controlled budget experiment** that locates the crossover under a
   configured schema-token budget (a real cost/latency policy);
2. an **adaptive retrieval gate** calibrated to that crossover — a no-regret
   guard that removes the −0.125 loss;
3. a **follow-up blog** with the "context windows ate this problem" thesis.

## Current behaviour (the gap, in code)

- `src/nl2sql/pipeline/retrieve.py` **always** runs retrieval and caps at
  `DEFAULT_MAX_TABLES = 8` (`src/nl2sql/schema_index/__init__.py:39`). On a db
  that fits, this unconditionally narrows to 8 and can drop a needed table — the
  −0.125 mechanism.
- The only adaptivity is the loop-aware `floor` widening on a **not-found
  execution error** (issue #46). But Step 5/6 showed failures are
  **wrong-answers**, not not-found errors, so the widening path rarely fires for
  the cases that actually fail. There is **no** "should I retrieve at all?"
  decision today.

## The deliverables

1. **Issue 1 (#75) — controlled budget experiment + crossover threshold.** A
   frozen, seeded slice spanning small-fit and the largest BIRD dev dbs. Under a
   *configured schema-token budget*, compare **naive-truncate-to-budget** vs
   **RAG-select-to-budget**, sweep the budget, and locate the crossover (below →
   dump wins, above → RAG wins). Explicitly labeled a controlled
   mechanism/threshold demo — BIRD never overflows context naturally.

2. **Issue 2 (#76) — budget-aware adaptive retrieval gate.** Full dump when the
   schema fits the configured budget; RAG selection when it exceeds it (threshold
   calibrated to the issue-1 crossover). Report naive / always-RAG / adaptive.
   This is the loop closing: a measured finding shaping the architecture.

3. **Follow-up blog** (after both issues land, per the per-issue workflow).
   Thesis: *schema-RAG mattered when context windows were tiny; with 200K-token
   windows its value has narrowed to genuine enterprise scale, which BIRD doesn't
   contain. Here's the crossover, and an adaptive gate that retrieves only past
   it.* Assembles from the committed `RESULTS.md` rows — honest by construction.

## Definition of done (follow-up)

- `RESULTS.md` rows record the budget sweep (naive-truncate vs RAG-select) and
  the identified crossover, labeled as a controlled experiment (no
  natural-overflow claim).
- A `RESULTS.md` row compares naive / always-RAG / adaptive on the crossover
  slice, showing adaptive ≥ max(naive, always-RAG) per regime (no regression).
- The crossover budget is stated and reproducible — material the blog assembles
  from.
- `uv run pytest` green; lint/format clean; module boundaries + import-sharing
  intact (the demo and harness use the same gate).
- Follow-up blog written under `docs/blogs/`, every claim tracing to a committed
  `RESULTS.md` row.

## Issues

- `issue-1-budget-crossover-experiment.md` — [#75](https://github.com/chiajung-wang/nl2sql-eval/issues/75) (controlled budget experiment + crossover)
- `issue-2-adaptive-retrieval-gate.md` — [#76](https://github.com/chiajung-wang/nl2sql-eval/issues/76) (adaptive gate, blocked by #75)

---

## Outcome (shipped — 2026-06-15)

The plan above expected a clean crossover (#75) and adaptive ≥ both baselines
(#76). What the paid runs (`claude-sonnet-4-6`, frozen `step6-large-schema-retrieval-lift`
slice) actually showed, and how the framing was corrected:

**#75 — budget crossover.** RAG-select beats naive-truncation at every swept
budget (gap +0.025–+0.100, peak @512t), recall climbs 0.450→1.000. **But** the
modes converge at **4096t** (selection divergence 0 — every schema fits, identical
prompts), where they still differ by +0.050: that is a **sampling-noise floor**
(temperature>0, 40 questions). Read against it, the pass@1 gaps are *suggestive,
not conclusive*; **recall is the robust signal**. Convergence is defined on
selection divergence (which noise can't move), not on the accuracy gap.

**#76 — adaptive gate (+ cost-axis fix).** naive full dump **0.675** / always-RAG
(capped) **0.625** / adaptive@2048t **0.675** (gate routed 24/40 full, 16/40 RAG).
Adaptive ties the ceiling and edges always-RAG by +0.050 — **within the ~0.05 noise
floor**, and the Step-6 −0.125 loss did **not** reproduce this run. So the gate's
value is **structural / no-regret** (a deterministic per-db full-vs-RAG choice that
never pays the table-cap's drop risk where the schema fits), not a measured accuracy
lift. `budget_tokens=None` keeps the prior always-RAG behaviour. **Cost axis** (the
gate's lever, rendered-schema tokens): adaptive matches naive's accuracy at **35%
fewer schema tokens** with a **per-call max bounded by the budget (2,038 ≤ 2,048)**,
where naive runs to 3,820. Quantifying cost also caught a defect — the gate's RAG
branch was table-capped, not budget-bounded, so it could blow the ceiling on a
few-but-large-table db; the fix fits the RAG branch to the budget.

**Net.** The honest thesis the blog tells: with modern context windows, schema-RAG's
value on a public benchmark has migrated from *fitting the schema* to *cost
control*; the gate does the second job and provably never regresses. The apparatus
caught three overclaims mid-flight (the "schemas exceed 4096t" claim, "beats at
every budget", "recovers the −0.125") — each fixed in a traceable commit.
