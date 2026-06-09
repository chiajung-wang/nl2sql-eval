# Plan — Step 3: Minimal harness + first BIRD slice numbers

**Phase:** Foundation (measurement apparatus) — **PHASE 1 DEFINITION OF DONE**
**Headline:** Produce the first *trustworthy* measured claim.

## Goal
Wire the batch harness and produce the first real pass@1 number on BIRD — using the now-validated comparator from Step 2. This is the project's thesis made concrete: a measured claim, not a working toy.

## Prerequisites
- Step 1 (pipeline) and **Step 2 (validated comparator)** — do not skip; an unvalidated harness producing BIRD numbers is the flashy-but-shallow trap.

## What to build
1. **`eval/harness.py`** — batch runner: iterate a test set, invoke the pipeline (shared import, not a copy), score each via `compare.py`, bucket the terminal state. Emit **pass@1** (no correction exists yet, so pass@1 is the only meaningful metric this step).
   - **Batch-capable, offline, repeatable** by design — this is what enables prompt-CI later. Make it invokable as a job, not only behind the demo.
2. **`eval/datasets/bird/`** — loader/adapter for BIRD (SQLite, file-per-db). Run each question against its **tagged** db (single-db per run; no routing).
3. **Frozen slice** — pick the Step 3 slice from **smaller-schema** BIRD dbs first, seeded and **checked into the repo as an explicit ID list**. Rationale: with no retrieval yet, the full schema is dumped into the prompt; large-schema dbs would overflow context / tank accuracy for reasons unrelated to generation quality. Small-schema-first keeps the first number trustworthy.
4. **`eval/metrics.py`** — accuracy aggregation + the terminal-state classifier (lives here, not in `state.py`).

## Done when
You have your first real **pass@1** on the frozen, small-schema BIRD slice, produced by a validated comparator.

## Results log (STARTS HERE — now mandatory)
Append to `RESULTS.md`: **date, model, slice ID, prompt version, commit, pass@1 number**, and a one-line note ("naive schema-dump baseline, small-schema slice"). From here on, **no step's done-when is met until its number is in `RESULTS.md` with full config.**

## Framing note (important)
This pass@1 is the **naive-schema-dump baseline**. Name it as such — it's the "before" that Step 6's retrieval will lift. A modest number here is a *feature* of the narrative, not a failure, as long as it's labeled.

## Pitfalls
- Don't let the slice include large-schema dbs yet (contaminates the baseline with context-overflow effects).
- Don't string-compare SQL anywhere — only result sets, via `compare.py`.
- Keep the harness's pipeline invocation identical to the demo's (shared import) to prevent drift.
