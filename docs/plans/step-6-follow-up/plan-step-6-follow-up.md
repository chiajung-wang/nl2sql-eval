# Plan — Step 6 follow-up: complete the retrieval-lift story (honestly)

**Phase:** Step 6 (Measured features) — *follow-up, pre-blog*

## Why this exists

Step 6 (issue #49) reported a retrieval lift of **−0.125** (pass@1 0.700 → 0.575)
with recall **0.942**. The finding is correct and honest, but it only shows the
regime where retrieval **costs** accuracy. The natural question — "where does
retrieval *pay*?" — turns out to have a sharp, current answer.

**The key fact we established:** there is **no BIRD database large enough for
retrieval to help.** The largest dev schema is `formula_1` (13 tables) /
`european_football_2` (~7.3K chars ≈ ~1.8K tokens) — both fit a 200K-token
context window trivially. With modern context windows, schema-RAG's original
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

- `issue-1-overflow-scale-slice-and-lift.md` — [#75](https://github.com/chiajung-wang/nl2sql-eval/issues/75) (controlled budget experiment + crossover)
- `issue-2-adaptive-retrieval-gate.md` — [#76](https://github.com/chiajung-wang/nl2sql-eval/issues/76) (adaptive gate, blocked by #75)
