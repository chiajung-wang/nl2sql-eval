# Issue 3 — Targeted prompting (few-shot + output-precision) + A/B

**Type:** AFK
**Phase:** Step 11 (Optimization) — *Closing the accuracy gap*

## Parent

`docs/plans/step-11/plan-step-11.md`

## What to build

The **second genuine-failure cluster** the diagnostic named: **distinct / projection** mismatches — the model adds or omits `DISTINCT` and returns the wrong number of output columns (`distinct_mismatch` 10, `projection_count_mismatch` 7).

- Add **few-shot exemplars** (`question → SQL` pairs covering the failure patterns) and **output-precision rules** (exactly which columns the answer wants, when to dedupe) to a generate template variant.
- **Leakage rule (critical):** the exemplars must come from **outside every eval slice** — other BIRD questions or the payments set — never from the dev or held-out slices, or you've trained on the test.
- **A/B on the dev (Step-3) slice**; report pass@1 before/after + the **distinct/projection bucket movement** from the re-run diagnostic.
- **Confirm the lift on the held-out slice** (`step11-holdout`) — few-shot is the highest overfitting-risk lever, so the held-out number is the real claim; touch it once.

## Acceptance criteria

- [ ] Few-shot + output-precision prompt variant; prompts stay externalized; exemplars sourced from outside all eval slices (no leakage)
- [ ] Dev A/B + the diagnostic's distinct/projection bucket movement, in `RESULTS.md`
- [ ] **Held-out lift confirmed** on `step11-holdout`; both dev and held-out numbers recorded with full config + commit
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) — the diagnostic that named this cluster. Independent of [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112).

---

## Tracking

**GitHub:** [#113](https://github.com/chiajung-wang/nl2sql-eval/issues/113) · label `agent-ready`, `step-11`

**PR:** _pending_

**Blocked by (GitHub):** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111)

**Step 11 set:** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) · [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112) · [#113](https://github.com/chiajung-wang/nl2sql-eval/issues/113)
