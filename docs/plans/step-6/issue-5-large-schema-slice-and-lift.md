# Issue 5 — Large-schema slice + retrieval lift + RESULTS.md (Step 6 DoD)

**Type:** AFK
**Phase:** Step 6 (Measured features) — *Schema-RAG + retrieval-recall + table-scope guard* · **Step 6 Definition of Done**

## Parent

`docs/plans/step-6/plan-step-6.md`

## What to build

Expand the frozen BIRD slice to **large-schema** dbs — where retrieval earns its keep — and record the **retrieval lift** vs the Step 3 naive-dump baseline. This is the second of the two sharpest findings.

- Extend the frozen, seeded, stratified slice to include large-schema dbs; keep it checked in as an explicit ID list (CI deltas stay clean).
- Run the harness with retrieval on; capture accuracy, retrieval recall, pass@1/pass@k.
- Append a `RESULTS.md` row with the **naive-baseline → retrieval lift** (before/after accuracy) and the retrieval-recall number, with full config (model, slice ID, prompt version, date, commit).

## Acceptance criteria

- [ ] Frozen slice extended to large-schema dbs; still seeded, stratified, checked-in as an explicit ID list
- [ ] Harness run reports accuracy + retrieval recall (+ pass@1/pass@k) on the expanded slice
- [ ] `RESULTS.md` row records naive-baseline → retrieval lift and retrieval recall with full config
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) (retrieve), [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46) (re-trigger), [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47) (recall metric), [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48) (table-scope guard).

---

## Tracking

**GitHub:** [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49) · label `agent-ready`, `step-6`

**PR:** _pending_

**Blocked by (GitHub):** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45), [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46), [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47), [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48)

**Step 6 set:** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) · [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46) · [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47) · [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48) · [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49)
