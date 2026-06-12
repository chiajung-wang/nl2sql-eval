# Issue 3 — Retrieval-recall metric (vs gold query's tables)

**Type:** AFK
**Phase:** Step 6 (Measured features) — *Schema-RAG + retrieval-recall + table-scope guard*

## Parent

`docs/plans/step-6/plan-step-6.md`

## What to build

Add the **retrieval-recall** eval axis: recall of the retrieved tables vs the **gold query's actual tables**. This is how the *silent* wrong-schema failure (valid SQL, wrong tables, no error, wrong-but-unsuspicious answer) gets **measured** even though it cannot be fixed at runtime.

- Extract the set of tables the gold query actually references; compare against the set the retriever returned; compute recall.
- Report retrieval recall in `metrics.py` alongside accuracy, per the harness's existing aggregation.
- Do **not** try to "fix" the silent case — measuring it is the deliverable (trying to fix it is trying to solve Text-to-SQL).

## Acceptance criteria

- [ ] `metrics.py` computes retrieval recall = |retrieved ∩ gold-tables| / |gold-tables|
- [ ] Gold-table extraction is deterministic (sqlglot AST, not string matching)
- [ ] Retrieval recall is reported alongside accuracy in the harness output
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) — the schema-RAG retrieve stage.

---

## Tracking

**GitHub:** [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47) · label `agent-ready`, `step-6`

**PR:** _pending_

**Blocked by (GitHub):** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45)

**Step 6 set:** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) · [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46) · [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47) · [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48) · [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49)
