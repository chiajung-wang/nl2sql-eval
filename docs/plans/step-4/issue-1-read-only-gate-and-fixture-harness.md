# Issue 1 — Read-only gate + guard wiring + fixture harness

**Type:** AFK
**Phase:** Step 4 (Measured features) — *Guardrails proven against a red-team fixture*

## Parent

`docs/plans/step-4/plan-step-4.md`

## What to build

The Step 4 tracer bullet: a deterministic, pre-execution guardrail gate wired end-to-end through the pipeline, plus the fixture-driven test harness everything else hangs off.

- In `pipeline/guard.py`, parse the candidate SQL into a **sqlglot AST** and enforce **read-only**: reject any write or DDL statement (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, …) **by AST statement type — never regex, never an LLM**.
- Wire `guard` into `graph.py` as the stage **between `generate` and `execute`**. On a guard failure the run does not execute; the harness classifies it as the `GUARDRAIL_REJECTED` terminal state (enum already in `state.py`; classifier stays in the harness).
- Stand up `fixtures/redteam_guard/` as a named deliverable: a machine-readable fixture format where each case carries the offending SQL and its **expected guardrail verdict**. Seed it with a handful of write/DDL attempts plus a couple of benign read-only `SELECT`s (expected: allowed).
- Stand up the **fixture-driven test harness** in `tests/` that runs `guard.py` over every fixture case and asserts the verdict, and a **catch-rate measurement seam** (the fixture's caught/total) that Step 4's DoD issue will report.

This establishes the full vertical — AST → gate → terminal state → fixture → measured number — so issues #2–#4 only add checks and cases.

## Acceptance criteria

- [ ] `guard.py` parses candidate SQL with sqlglot and rejects writes/DDL by AST statement type (no regex, no LLM)
- [ ] Benign read-only `SELECT` queries pass the gate
- [ ] `guard` runs between `generate` and `execute` in `graph.py`; rejected runs are classified `GUARDRAIL_REJECTED` by the harness (not in `state.py`)
- [ ] `fixtures/redteam_guard/` holds a machine-readable fixture with per-case expected verdicts, seeded with write/DDL and benign cases
- [ ] Fixture-driven tests assert every case's verdict and expose a catch-rate (caught/total) seam
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

None — can start immediately.

---

## Tracking

**GitHub:** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32) · label `agent-ready`, `step-4`

**PR:** [#36](https://github.com/chiajung-wang/nl2sql-eval/pull/36) → `step-4/guardrails-and-redteam` · summary `docs/plans/step-4/issue-1-summary.html`

**Blocked by (GitHub):** None — can start immediately

**Step 4 set:** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32) · [#33](https://github.com/chiajung-wang/nl2sql-eval/issues/33) · [#34](https://github.com/chiajung-wang/nl2sql-eval/issues/34) · [#35](https://github.com/chiajung-wang/nl2sql-eval/issues/35)
