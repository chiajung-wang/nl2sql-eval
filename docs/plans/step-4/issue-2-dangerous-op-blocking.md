# Issue 2 — Dangerous-op blocking

**Type:** AFK
**Phase:** Step 4 (Measured features) — *Guardrails proven against a red-team fixture*

## Parent

`docs/plans/step-4/plan-step-4.md`

## What to build

Extend the deterministic guardrail gate to block destructive/unsafe constructs **beyond** plain writes/DDL — still sqlglot-AST only, no regex, no LLM.

Targets (parse from the AST, reject on match):
- **Multiple statements** in one candidate (stacked-query / statement-injection shape).
- **`ATTACH` / `DETACH` DATABASE** (SQLite data-boundary escape).
- **Write-bearing `PRAGMA`** and other side-effecting meta-statements.
- Any other destructive construct surfaced by the red-team fixture that read-only typing alone misses.

Failing cases land in `GUARDRAIL_REJECTED` exactly like #1. Add the corresponding red-team cases to `fixtures/redteam_guard/` (offending SQL + expected verdict) so they flow through the existing fixture-driven test harness.

## Acceptance criteria

- [ ] Gate rejects multi-statement candidates, `ATTACH`/`DETACH`, and write-bearing `PRAGMA` via the AST (no regex, no LLM)
- [ ] New dangerous-op cases added to `fixtures/redteam_guard/` with expected verdicts
- [ ] All new cases pass through the existing fixture-driven test harness and contribute to the catch-rate seam
- [ ] No table-scope enforcement introduced (that is Step 6)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- #32 (read-only gate + fixture harness)

---

## Tracking

**GitHub:** [#33](https://github.com/chiajung-wang/nl2sql-eval/issues/33) · label `agent-ready`, `step-4`

**PR:** [#37](https://github.com/chiajung-wang/nl2sql-eval/pull/37) → `step-4/guardrails-and-redteam` · summary `docs/plans/step-4/issue-2-summary.html`

**Blocked by (GitHub):** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32)

**Step 4 set:** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32) · [#33](https://github.com/chiajung-wang/nl2sql-eval/issues/33) · [#34](https://github.com/chiajung-wang/nl2sql-eval/issues/34) · [#35](https://github.com/chiajung-wang/nl2sql-eval/issues/35)
