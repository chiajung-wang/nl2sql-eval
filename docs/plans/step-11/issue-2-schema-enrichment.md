# Issue 2 — Schema enrichment (FK relationships + sample values) + A/B

**Type:** AFK
**Phase:** Step 11 (Optimization) — *Closing the accuracy gap*

## Parent

`docs/plans/step-11/plan-step-11.md`

## What to build

The **#1 lever** the error analysis named: the dominant genuine-failure bucket is **wrong tables / wrong join path** (`table_mismatch` 9 + `join_mismatch` 7) — the model doesn't know the foreign-key relationships or which table holds which column, even on ≤5-table schemas. Enrich the schema the generator sees.

- Add a **`v4` generate template** (a clean-diff `{% extends %}` over the shared scaffold — Step 9 structure) that injects, alongside the DDL:
  - **explicit foreign-key relationships** (which column joins to which), and
  - a few **sample column values** per table (so the model knows the value spellings / formats).
- **A/B vs the naive dump** on the frozen Step-3 slice; append pass@1 before/after to `RESULTS.md` (strict **and** BIRD set-semantics).
- **Re-run the diagnostic** and show the **join/table bucket shrank** — the point is to prove the targeted bucket moved, not just the headline.
- Prompt-CI (Step 9) guards the prompt change against regressions.

## Acceptance criteria

- [ ] `v4` generate template injects FK relationships + sample values; prompts stay externalized (no inline strings)
- [ ] A/B on the frozen slice: pass@1 before/after recorded in `RESULTS.md` with full config + commit
- [ ] The re-run diagnostic shows the table/join bucket movement (the lever hit its target — or an honest null with the reason)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) — the diagnostic that named this lever.

---

## Tracking

**GitHub:** [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112) · label `agent-ready`, `step-11`

**PR:** _pending_

**Blocked by (GitHub):** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111)

**Step 11 set:** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) · [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112) · [#113](https://github.com/chiajung-wang/nl2sql-eval/issues/113)
