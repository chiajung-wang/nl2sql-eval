# Plan — Step 5: Self-correction (execution-error feedback) + pass@k

**Phase:** Measured features
**Headline:** Quantify what self-correction is actually worth.

## Goal
Turn the single-shot generator into an **agent** by adding a correction loop driven by **execution-error feedback only**, and extend the harness to report **pass@1 AND pass@k**. The gap between them is a headline finding.

## Prerequisites
- Step 3 (harness emitting pass@1).
- Step 4 (guard gate; guardrail rejections can also feed correction).

## What to build
1. **`pipeline/correct.py`** — on execution failure (syntax error, etc.), feed the error message back and regenerate. **Capped retry budget** (prevents infinite loops and runaway cost; the cap is itself a cost/latency lever to discuss).
2. **`pipeline/graph.py`** — add the conditional loop-back edge (`execute → correct → generate`) with the cap and terminal-state transitions (`retry_exhausted`, `execution_error_final`).
3. **Harness extension** — emit both:
   - **pass@1**: generator alone, no correction.
   - **pass@k**: with the correction budget.
   - Plus per-question **attempts** and **cost/latency**, so the recovery is not "free" in the numbers.

## Explicitly NOT in this step
**Retrieval re-trigger.** Schema-RAG does not exist until Step 6, so the loop here handles execution-error feedback only. The retrieval re-trigger (re-fetching on column/table-not-found) is a **Step 6** contribution. (This was a corrected ordering bug — Step 5 cannot re-trigger retrieval that doesn't yet exist.)

## Done when
You can state the **pass@1 → pass@k gap** — e.g. "self-correction recovers X% of initial failures at a cost of Y% added latency."

## Results log
Append **pass@1, pass@k, the gap, and the added cost/latency** with config + commit. This is one of the two sharpest findings — capture it now, don't reconstruct it later.

## Pitfalls
- Self-correction can **mask** problems: silent retries that eventually stumble into the right answer make accuracy look good while latency/cost quietly balloon. Reporting both numbers + cost is the guard against this.
- Keep the retry cap explicit and configurable.
