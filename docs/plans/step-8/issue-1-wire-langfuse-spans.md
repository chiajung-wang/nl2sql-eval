# Issue 1 — Wire pipeline stage seams to Langfuse spans

**Type:** AFK
**Phase:** Step 8 (Operations) — *Observability + redacted-logging*

## Parent

`docs/plans/step-8/plan-step-8.md`

## What to build

The Step 8 tracer bullet: wire each pipeline stage's existing thin obs seam to a **Langfuse** span so every run becomes a trace whose spans mirror the stages.

- Connect the seams added stage-by-stage during Steps 1–7 to Langfuse spans: `retrieve`, `generate`, `guard`, `execute`, `correct`, `redact`.
- Capture **cost / latency / tokens** natively per span (feeds the pass@1-vs-pass@k cost analysis).
- If a seam is missing from an earlier stage, add the seam, then wire it — do not retrofit instrumentation wholesale.

## Acceptance criteria

- [ ] Each pipeline stage emits a Langfuse span; one run = one trace with spans mirroring the stages
- [ ] Cost, latency, and tokens are captured per span
- [ ] Missing seams are added at the seam level (not bulk-retrofitted)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- Steps 1–7, where each stage got a thin obs seam as it was built. Direct predecessor: [#52](https://github.com/chiajung-wang/nl2sql-eval/issues/52).

---

## Tracking

**GitHub:** [#54](https://github.com/chiajung-wang/nl2sql-eval/issues/54) · label `agent-ready`, `step-8`

**PR:** _pending_

**Blocked by (GitHub):** [#52](https://github.com/chiajung-wang/nl2sql-eval/issues/52) (Steps 1–7 complete)

**Step 8 set:** [#54](https://github.com/chiajung-wang/nl2sql-eval/issues/54) · [#55](https://github.com/chiajung-wang/nl2sql-eval/issues/55) · [#56](https://github.com/chiajung-wang/nl2sql-eval/issues/56)
