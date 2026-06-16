# Issue 3 — Cross-provider table (accuracy × cost × latency) + RESULTS.md (Step 7 DoD)

**Type:** AFK
**Phase:** Step 7 (Framework / provider) — *only AFTER logic is proven* · **Step 7 Definition of Done**

## Parent

`docs/plans/step-7/plan-step-7.md`

## What to build

Run the harness across providers/models and produce a **cross-provider comparison table** of accuracy × cost × latency — turning "model selection / cost-latency-quality trade-offs" into a concrete eval artifact.

- Run the frozen slice through the harness for each selected provider/model. OpenRouter's single-key, many-model access (via the LiteLLM boundary) makes broadening the table cheap; use direct provider keys where you want native list pricing.
- Produce a table: model, accuracy (pass@1/pass@k), cost, latency.
- **Record the cost basis per row** — OpenRouter reports *its own* normalized/marked-up price (queryable via its generation endpoint), not the provider's direct list price; a mixed table must say which basis each row uses.
- For any OpenRouter row, pin provider routing (`allow_fallbacks: false`) so the frozen slice stays repeatable (PRD §9).
- Append a `RESULTS.md` entry with the post-refactor parity numbers and the cross-provider table, with full config (slice ID, prompt version, date, commit).

## Acceptance criteria

- [ ] Harness runs across ≥2 providers/models on the frozen slice
- [ ] Cross-provider table produced: model × accuracy × cost × latency, with the **cost basis** (direct list vs. OpenRouter) noted per row
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
