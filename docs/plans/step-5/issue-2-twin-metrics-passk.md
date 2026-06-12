# Issue 2 — Twin metrics: pass@1 AND pass@k (+ attempts/cost/latency)

**Type:** AFK
**Phase:** Step 5 (Measured features) — *Self-correction + pass@k*

## Parent

`docs/plans/step-5/plan-step-5.md`

## What to build

Extend the harness to report the **twin metrics** that make self-correction's value legible — and make sure recovery is never "free" in the numbers.

- Emit **pass@1**: the generator alone, no correction (first attempt only).
- Emit **pass@k**: the same questions run with the full correction budget enabled.
- Record per-question **attempts**, **cost**, and **latency**, so the pass@1→pass@k lift is always shown against its added cost/latency.
- The gap between pass@1 and pass@k is a headline finding; the harness must compute it directly, not leave it to be reconstructed later.

## Acceptance criteria

- [ ] Harness emits both pass@1 (no correction) and pass@k (with the capped correction budget) over the same slice
- [ ] Per-question attempts, cost, and latency are captured and aggregated
- [ ] The pass@1→pass@k gap is computed and surfaced alongside the added cost/latency
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42) — the correction loop (pass@k is meaningless without it).

---

## Tracking

**GitHub:** [#43](https://github.com/chiajung-wang/nl2sql-eval/issues/43) · label `agent-ready`, `step-5`

**PR:** _pending_

**Blocked by (GitHub):** [#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42)

**Step 5 set:** [#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42) · [#43](https://github.com/chiajung-wang/nl2sql-eval/issues/43) · [#44](https://github.com/chiajung-wang/nl2sql-eval/issues/44)
