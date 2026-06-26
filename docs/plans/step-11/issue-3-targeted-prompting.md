# Issue 3 — Targeted prompting (few-shot + output-precision) + A/B

**Type:** AFK
**Phase:** Step 11 (Optimization) — *Closing the accuracy gap*

## Parent

`docs/plans/step-11/plan-step-11.md`

## What to build

The **second genuine-failure cluster** the diagnostic named: **distinct / projection** mismatches — the model adds or omits `DISTINCT` and returns the wrong number of output columns (`distinct_mismatch` 10, `projection_count_mismatch` 7).

- Add **few-shot exemplars** (`question → SQL` pairs covering the failure patterns) and **output-precision rules** (exactly which columns the answer wants, when to dedupe) to a generate template variant.
- **A/B vs baseline** on the frozen Step-3 slice; append pass@1 before/after to `RESULTS.md`, and report the **distinct/projection bucket movement** from the re-run diagnostic.
- **Mind overfitting** the small (50-question) frozen slice — note the caveat, or confirm the lift on a held-out slice before claiming it.

## Acceptance criteria

- [ ] Few-shot + output-precision prompt variant; prompts stay externalized
- [ ] A/B on the frozen slice recorded in `RESULTS.md` with full config + commit
- [ ] Distinct/projection bucket movement reported via the re-run diagnostic; overfitting caveat addressed
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) — the diagnostic that named this cluster. Independent of [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112).

---

## Tracking

**GitHub:** [#113](https://github.com/chiajung-wang/nl2sql-eval/issues/113) · label `agent-ready`, `step-11`

**PR:** _pending_

**Blocked by (GitHub):** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111)

**Step 11 set:** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) · [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112) · [#113](https://github.com/chiajung-wang/nl2sql-eval/issues/113)
