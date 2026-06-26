# Plan — Step 11: Closing the Accuracy Gap

**Phase:** Optimization — *the baseline finally gets tuned*
**Headline:** Turn the honest 0.420 anchor into a measured improvement — diagnose the failures, fix the biggest bucket, prove each lift on the frozen slice.

## Goal
Steps 1–10 built and operated the system on a **deliberately unoptimized** baseline: pass@1 **0.420 (21/50)** is a naive schema dump, zero-shot, default model — an *honest anchor*, never a tuned result. Step 11 is the step that finally optimizes it, **measurement-first**: read what the failures actually are (error analysis), apply the targeted lever the analysis names, and A/B every change on the frozen slice so the lift (or honest null) is traceable to a config and commit.

The discipline that ran the whole project applies here: don't optimize on vibes. The diagnostic (#111) already named the targets — so every improvement is a hypothesis the diagnostic can confirm by showing its bucket shrank.

## Prerequisites
- The frozen, seeded, stratified slice + the batch harness (Step 3) — the A/B substrate.
- The proven comparator (Step 2), including `BIRD_RULES` set-semantics for scorer-vs-model separation.
- Externalized prompts + prompt-CI (Step 9) — every prompt edit re-runs the slice and posts the pass@1/pass@k delta, so an optimization that regresses is caught.

## What the diagnosis found (the starting point)
From the baseline error analysis (#111, `docs/plans/step-3/baseline-failures.md`):
- **pass@1 0.420 strict / 0.460 under BIRD's official set-semantics** — only **2/29** failures are scorer-strictness artifacts, so the number is honest and there is real accuracy to win.
- **27/29 failures are genuine model errors.** Dominant structural buckets: **table_mismatch (9) + join_mismatch (7)** — wrong tables / wrong join path even on ≤5-table schemas — then **distinct (10)** and **projection-count (7)**.
- **By difficulty: moderate is the worst (0.263)**, below challenging (0.429) and simple (0.542).

## What to build
1. **Baseline error-analysis diagnostic** (#111) — **done** (PR #110). `eval/diagnose_bird.py`: the failure taxonomy + the scorer-vs-genuine split. Establishes the targets above and is re-runnable to confirm a fix moved the right bucket.
2. **Schema enrichment** (#112) — the #1 lever. A `v4` generate template injecting **explicit foreign-key relationships** + a few **sample column values** alongside the DDL, so the model stops guessing join paths. A/B vs the naive dump on the frozen slice; report pass@1 before/after **and** the join/table bucket movement (re-run the diagnostic).
3. **Targeted prompting** (#113) — the second cluster. Few-shot exemplars + output-precision rules (which columns to return, when to dedupe) for the distinct/projection bucket. A/B on the frozen slice with bucket movement.

## Done when
At least one targeted lever lands a **measured pass@1 lift on the frozen slice** (or an honest, explained null), with the diagnostic showing the **targeted bucket shrank** — every number appended to `RESULTS.md` with its config and commit.

## Results log
Append before/after pass@1 for each lever (strict **and** BIRD set-semantics), plus the per-bucket movement from the re-run diagnostic. The headline is the **baseline → tuned** delta, with each gain attributed to the lever that produced it.

## Pitfalls
- **Optimize the bucket the diagnostic names, not a hunch** — and prove the bucket moved, not just the headline (a headline can move by luck on 50 questions).
- **Overfitting the small frozen slice** — it's 50 questions; a tuned prompt can memorize its quirks. Note the caveat, or confirm a lift on a held-out slice before claiming it.
- **Mind sampling noise** (~0.05 on 50 questions, temperature>0) — read small deltas against that floor, as Steps 5–6 did.
- **Prompt-CI is the guardrail** — let it catch a prompt change that regresses while chasing a different bucket.
