# Issue 2 — Loop-aware re-trigger (not-found error → re-retrieve)

**Type:** AFK
**Phase:** Step 6 (Measured features) — *Schema-RAG + retrieval-recall + table-scope guard*

## Parent

`docs/plans/step-6/plan-step-6.md`

## What to build

Make the correction loop **retrieval-aware**: a `column/table-not-found` execution error should feed back into **retrieval**, not only into generation.

- Detect not-found-class execution errors and route them as a re-retrieve signal into `pipeline/retrieve.py` (re-retrieve with the error as context), then regenerate.
- This closes the asymmetry from Step 5, where everything looped except retrieval (which was single-shot).
- Stays inside the **same capped retry budget** from Step 5 — re-retrieval is not a budget bypass.

## Acceptance criteria

- [ ] A `column/table-not-found` execution error triggers a re-retrieve (not only regeneration)
- [ ] Re-retrieval reuses the Step 5 capped budget; no infinite loop
- [ ] Demoable: a question that first retrieved the wrong tables recovers by re-retrieving on the not-found error
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) — the schema-RAG retrieve stage; and the Step 5 correction loop ([#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42)).

---

## Tracking

**GitHub:** [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46) · label `agent-ready`, `step-6`

**PR:** _pending_

**Blocked by (GitHub):** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45), [#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42)

**Step 6 set:** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) · [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46) · [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47) · [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48) · [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49)
