# Issue 1 — Schema-RAG retrieve stage (relevant-tables, not full dump)

**Type:** AFK
**Phase:** Step 6 (Measured features) — *Schema-RAG + retrieval-recall + table-scope guard*

## Parent

`docs/plans/step-6/plan-step-6.md`

## What to build

The Step 6 tracer bullet: replace the naive full-schema dump with **RAG over schema metadata** — retrieve only the tables relevant to *this* question — wired end-to-end through the pipeline.

- Build a schema index over **table definitions, column names/types, a few sample values per column** (knowing `status ∈ {failed, settled}` changes the SQL), and optional short descriptions.
- Implement `pipeline/retrieve.py` so the `generate` stage receives only the relevant tables instead of the full schema dump (the Step 3 naive baseline).
- Keep it the **same shared pipeline** the harness and demo import — no fork.

This is the vertical that the later slices (re-trigger, recall metric, table-scope guard, lift) all hang off.

## Acceptance criteria

- [ ] A schema index exists over table defs, column names/types, sample values per column, optional descriptions
- [ ] `pipeline/retrieve.py` returns only the relevant tables for a question; `generate` consumes that instead of the full dump
- [ ] Demoable on payments: a question retrieves its relevant tables and generates correct SQL from them
- [ ] No pipeline fork — harness and demo import the same retrieve stage
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

None — can start immediately (builds on the Step 3 harness, Step 4 guard, Step 5 loop).

---

## Tracking

**GitHub:** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) · label `agent-ready`, `step-6`

**PR:** _pending_

**Blocked by (GitHub):** None — can start immediately

**Step 6 set:** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) · [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46) · [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47) · [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48) · [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49)
