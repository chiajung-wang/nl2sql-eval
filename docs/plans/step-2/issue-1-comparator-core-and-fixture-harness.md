# Issue 1 — Comparator core & golden-fixture harness

**Type:** AFK
**Phase:** Step 2 (Foundation) — *Prove the scorer is trustworthy before trusting any number it produces*

## Parent

`docs/plans/step-2/plan-step-2.md`

## What to build

The thinnest end-to-end slice of the measurement core: a result-set comparator with a public `compare()` entry point, the checked-in golden-fixture format under `fixtures/golden_compare/`, and a fixture-driven test runner — all green on the simplest cases before any canonicalization nuance is added. This is the skeleton every later Step 2 slice extends.

Includes:
- **`eval/compare.py`** — a `compare(gold_result, candidate_result, gold_sql) -> verdict` API returning a clear correct/incorrect verdict. Comparison is on **result sets only — never SQL string-match** (CLAUDE.md §5.1, §7). Canonicalization rules are applied to *both* sides before comparison; the rule set is **configurable** and **logged per comparison** so every verdict is explainable. Only the trivial rules land in this slice (exact equality / plain difference); the subtle rules arrive in Issues 2–3.
- **`fixtures/golden_compare/`** — the named, checked-in deliverable: `(gold_result, candidate_result, expected_verdict)` triples in a committed, parseable format. Seed it with the baseline cases: identical result sets → correct, a plainly-different result set → wrong, and the **empty result** handled as a distinct correct-able case.
- **`tests/`** — a test that *loads the fixture* and asserts each triple's verdict, so the fixture (not hand-written asserts) is the source of truth. New fixture cases must be picked up automatically.

Scope guard: do not implement order-sensitivity, NULL/float/column canonicalization, multiset semantics, or BIRD reconciliation here — those are Issues 2–4. Keep `compare.py` deterministic: no LLM calls, no regex for SQL semantics.

## Acceptance criteria

- [ ] `eval/compare.py` exposes a `compare(gold_result, candidate_result, gold_sql)` API returning a correct/incorrect verdict, comparing result sets (never SQL strings).
- [ ] The canonicalization rule set is configurable and each comparison logs which rules were applied.
- [ ] `fixtures/golden_compare/` exists as a committed, parseable set of `(gold, candidate, expected_verdict)` triples.
- [ ] Baseline fixture cases are present and pass: identical → correct, plainly-different → wrong, empty-result → handled as its own correct-able case.
- [ ] A fixture-driven test loads the triples and asserts each verdict; adding a new triple is automatically exercised.
- [ ] `uv run pytest` passes; lint/format clean.

## Blocked by

None — can start immediately (Step 1 already produces result sets to compare).

---

## Tracking

**GitHub:** [#11](https://github.com/chiajung-wang/nl2sql-eval/issues/11) · label `agent-ready`, `step-2`

**Blocked by (GitHub):** None — can start immediately

**Step 2 set:** [#11](https://github.com/chiajung-wang/nl2sql-eval/issues/11) · [#12](https://github.com/chiajung-wang/nl2sql-eval/issues/12) · [#13](https://github.com/chiajung-wang/nl2sql-eval/issues/13) · [#14](https://github.com/chiajung-wang/nl2sql-eval/issues/14)
