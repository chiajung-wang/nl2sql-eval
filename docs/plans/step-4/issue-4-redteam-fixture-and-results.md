# Issue 4 — Red-team fixture completion + RESULTS.md catch-rate (Step 4 DoD)

**Type:** AFK
**Phase:** Step 4 (Measured features) — *Guardrails proven against a red-team fixture*

## Parent

`docs/plans/step-4/plan-step-4.md`

## What to build

Complete the red-team fixture as a finished **named deliverable** and report the measured safety claim — the Step 4 Definition of Done.

- Round out `fixtures/redteam_guard/` to cover the full surface: injected dangerous SQL (write attempts, drops, cartesian bombs, stacked statements, boundary escapes) **and** **prompt-injection-style natural-language prompts** that try to *induce* dangerous SQL, each labeled with its expected guardrail verdict. The SQL-level cases drive deterministic unit tests; the NL-induction cases are exercised through the end-to-end `generate → guard` path and reported as a measured catch rate.
- Compute the **red-team catch rate** (N% of dangerous cases caught) from the fixture-driven harness.
- Append the catch-rate result to `RESULTS.md` with the full config: **model, slice/fixture ID, prompt version, date, the number, and the commit** — per the running-results discipline.

## Acceptance criteria

- [ ] `fixtures/redteam_guard/` is the complete named deliverable: dangerous-SQL cases + prompt-injection NL prompts, each with expected verdict
- [ ] Guardrails are unit-test green against the entire fixture
- [ ] Red-team **catch rate (N% caught)** is computed and stated
- [ ] `RESULTS.md` has a Step 4 entry: model, fixture/slice ID, prompt version, date, catch-rate number, commit
- [ ] Statement holds: "caught N% of red-team queries"
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- #32 (read-only gate + fixture harness)
- #33 (dangerous-op blocking)
- #34 (cost/complexity heuristic)

---

## Tracking

**GitHub:** [#35](https://github.com/chiajung-wang/nl2sql-eval/issues/35) · label `agent-ready`, `step-4`

**PR:** [#39](https://github.com/chiajung-wang/nl2sql-eval/pull/39) → `step-4/guardrails-and-redteam` · summary `docs/plans/step-4/issue-4-summary.html`

**Result:** red-team catch rate **1.000 (29/29)** — `RESULTS.md`, commit `e56fbcd`

**Blocked by (GitHub):** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32) · [#33](https://github.com/chiajung-wang/nl2sql-eval/issues/33) · [#34](https://github.com/chiajung-wang/nl2sql-eval/issues/34)

**Step 4 set:** [#32](https://github.com/chiajung-wang/nl2sql-eval/issues/32) · [#33](https://github.com/chiajung-wang/nl2sql-eval/issues/33) · [#34](https://github.com/chiajung-wang/nl2sql-eval/issues/34) · [#35](https://github.com/chiajung-wang/nl2sql-eval/issues/35)
