# Issue 3 — Cost/complexity heuristic (heuristic-first)

**Type:** AFK
**Phase:** Step 4 (Measured features) — *Guardrails proven against a red-team fixture*

## Parent

`docs/plans/step-4/plan-step-4.md`

## What to build

Add the **cost/complexity heuristic** to the guardrail gate — **heuristic-first**, derived entirely from the sqlglot AST. No `EXPLAIN` (BIRD is SQLite, which has no cost-bearing EXPLAIN; EXPLAIN-based cost is a Postgres-only enhancement deferred to a later step).

Heuristic signals from the AST:
- **Join count** over a configurable threshold.
- **Missing `LIMIT`** on a broad/unbounded result.
- **Cartesian product** detection (cross join / join without an `ON`/`USING` predicate).

On trip, the run is rejected (`GUARDRAIL_REJECTED`) or, once Step 5's corrector exists, fed back as a correction signal — for now, reject. Thresholds live in code/config, not magic numbers scattered around. Add cartesian-bomb and unbounded-scan cases to `fixtures/redteam_guard/` flowing through the existing fixture-driven harness.

## Acceptance criteria

- [ ] Heuristic computes join-count, missing-`LIMIT`, and cartesian-product purely from the sqlglot AST
- [ ] No `EXPLAIN` / cost-estimator dependency on the SQLite path
- [ ] Tripping the heuristic yields `GUARDRAIL_REJECTED`
- [ ] Cartesian-bomb and unbounded-scan cases added to `fixtures/redteam_guard/` with expected verdicts
- [ ] Thresholds are named/configurable, not inline magic numbers
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- #32 (read-only gate + fixture harness)

---

## Tracking

**GitHub:** [#34](https://github.com/chiajung-wang/nl2sql-eval/issues/34) · label `agent-ready`, `step-4`

**PR:** [#38](https://github.com/chiajung-wang/nl2sql-eval/pull/38) → `step-4/guardrails-and-redteam` · summary `docs/plans/step-4/issue-3-summary.html`

**Blocked by (GitHub):** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32)

**Step 4 set:** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32) · [#33](https://github.com/chiajung-wang/nl2sql-eval/issues/33) · [#34](https://github.com/chiajung-wang/nl2sql-eval/issues/34) · [#35](https://github.com/chiajung-wang/nl2sql-eval/issues/35)
