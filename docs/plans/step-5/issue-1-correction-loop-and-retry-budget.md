# Issue 1 — Correction loop (execution-error feedback) + capped retry budget

**Type:** AFK
**Phase:** Step 5 (Measured features) — *Self-correction + pass@k*

## Parent

`docs/plans/step-5/plan-step-5.md`

## What to build

The Step 5 tracer bullet: turn the single-shot generator into an **agent** by adding an execution-error-driven correction loop, wired end-to-end through the pipeline with a **capped retry budget**.

- Add `pipeline/correct.py`: on an execution failure (syntax error, runtime error), capture the error message and feed it back as a correction signal that re-triggers `generate`.
- Wire the conditional loop-back edge in `pipeline/graph.py`: `execute → correct → generate`, governed by a **configurable, capped retry budget** (prevents infinite loops and runaway cost — the cap is itself a cost/latency lever).
- Add the terminal-state transitions: a run that recovers ends `success`; a run that exhausts the budget ends `retry_exhausted`; a final unrecoverable execution error ends `execution_error_final`. Enum stays in `state.py`; the classifier stays in the harness.
- **Scope:** execution-error feedback only. Retrieval re-trigger is deferred to Step 6 (schema-RAG does not exist yet — the loop cannot re-trigger retrieval that does not exist).

This establishes the full vertical — error → correct → regenerate → capped loop → terminal state — so the metric work (Issue 2) only needs to read the loop's attempt counts.

## Acceptance criteria

- [ ] `pipeline/correct.py` feeds the execution-error message back into `generate` as a correction signal
- [ ] `graph.py` has the `execute → correct → generate` loop-back edge with a configurable retry cap
- [ ] Recovered run → `success`; budget exhausted → `retry_exhausted`; final execution error → `execution_error_final` (enum in `state.py`, classifier in harness)
- [ ] No retrieval re-trigger in this step (execution-error feedback only)
- [ ] Demoable end-to-end on the payments gold set (a deliberately broken first attempt recovers within budget)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

None — can start immediately (builds on the Step 3 harness and Step 4 guard gate).

---

## Tracking

**GitHub:** [#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42) · label `agent-ready`, `step-5`

**PR:** _pending_

**Blocked by (GitHub):** None — can start immediately

**Step 5 set:** [#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42) · [#43](https://github.com/chiajung-wang/nl2sql-eval/issues/43) · [#44](https://github.com/chiajung-wang/nl2sql-eval/issues/44)
