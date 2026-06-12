# Issue 4 — Table-scope guardrail (per-db allowed tables)

**Type:** AFK
**Phase:** Step 6 (Measured features) — *Schema-RAG + retrieval-recall + table-scope guard*

## Parent

`docs/plans/step-6/plan-step-6.md`

## What to build

Complete the guardrail with **per-db table-scope enforcement** — deliberately deferred from Step 4 until the schema metadata that defines "allowed tables" exists.

- In `pipeline/guard.py`, add a deterministic **sqlglot AST** check that rejects a candidate query touching tables outside the per-db allowed-tables list (derived from schema metadata). No regex, no LLM.
- On fail: reject **or** feed back as a correction signal, consistent with the other guard checks.
- Extend `fixtures/redteam_guard/` with table-scope cases (queries touching out-of-scope tables) carrying their expected verdict, and report the catch rate.

## Acceptance criteria

- [ ] `guard.py` rejects queries touching tables outside the per-db allowed-tables list, by sqlglot AST (no regex, no LLM)
- [ ] In-scope queries pass; the check is deterministic
- [ ] `fixtures/redteam_guard/` gains table-scope cases with expected verdicts; catch rate reported
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) — the schema index (allowed-tables list comes from schema metadata).

---

## Tracking

**GitHub:** [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48) · label `agent-ready`, `step-6`

**PR:** _pending_

**Blocked by (GitHub):** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45)

**Step 6 set:** [#45](https://github.com/chiajung-wang/nl2sql-eval/issues/45) · [#46](https://github.com/chiajung-wang/nl2sql-eval/issues/46) · [#47](https://github.com/chiajung-wang/nl2sql-eval/issues/47) · [#48](https://github.com/chiajung-wang/nl2sql-eval/issues/48) · [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49)
