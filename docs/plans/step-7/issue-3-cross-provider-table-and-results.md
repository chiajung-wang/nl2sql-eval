# Issue 3 — Cross-provider table (accuracy × cost × latency) + RESULTS.md (Step 7 DoD)

**Type:** AFK
**Phase:** Step 7 (Framework / provider) — *only AFTER logic is proven* · **Step 7 Definition of Done**

## Parent

`docs/plans/step-7/plan-step-7.md`

## What to build

Run the harness across providers/models and produce a **cross-provider comparison table** of accuracy × cost × latency — turning "model selection / cost-latency-quality trade-offs" into a concrete eval artifact.

- Run the frozen slice through the harness for each selected provider/model.
- Produce a table: model, accuracy (pass@1/pass@k), cost, latency.
- Append a `RESULTS.md` entry with the post-refactor parity numbers and the cross-provider table, with full config (slice ID, prompt version, date, commit).

## Acceptance criteria

- [ ] Harness runs across ≥2 providers/models on the frozen slice
- [ ] Cross-provider table produced: model × accuracy × cost × latency
- [ ] `RESULTS.md` records post-refactor parity + the cross-provider table with full config
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#51](https://github.com/chiajung-wang/nl2sql-eval/issues/51) — the LiteLLM swap.

---

## Tracking

**GitHub:** [#52](https://github.com/chiajung-wang/nl2sql-eval/issues/52) · label `agent-ready`, `step-7`

**PR:** _pending_

**Blocked by (GitHub):** [#51](https://github.com/chiajung-wang/nl2sql-eval/issues/51)

**Step 7 set:** [#50](https://github.com/chiajung-wang/nl2sql-eval/issues/50) · [#51](https://github.com/chiajung-wang/nl2sql-eval/issues/51) · [#52](https://github.com/chiajung-wang/nl2sql-eval/issues/52)
