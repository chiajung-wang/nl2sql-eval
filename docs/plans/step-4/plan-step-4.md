# Plan — Step 4: Guardrails (schema-free) + red-team fixture

**Phase:** Measured features
**Headline:** A safety feature is only as good as the test that proves it works.

## Goal
Add the deterministic, pre-execution guardrail gate — scoped to the checks that need **no schema metadata** — and a red-team fixture that *measures* its effectiveness. Guardrails are deterministic (AST, not regex; not LLM-judged) so they are unit-testable and reportable as a measured claim.

## Prerequisites
- Step 1 (pipeline with an execute stage to gate).
- `sqlglot` (already available).

## What to build
1. **`pipeline/guard.py`** — deterministic gate between `generate` and `execute`, parsing the SQL into a `sqlglot` AST and checking:
   - **Read-only enforcement**: reject any `INSERT`/`UPDATE`/`DELETE`/`DROP`/DDL — by statement type from the AST, never regex.
   - **Dangerous-op blocking**: block other destructive/unsafe constructs.
   - **Cost/complexity heuristic** — **heuristic-FIRST** (join count, missing `LIMIT`, cartesian-product detection from the AST). EXPLAIN-based cost is a Postgres-only *enhancement* layered later; the heuristic is the primary path because BIRD is SQLite (no cost-bearing EXPLAIN), and BIRD drives the headline numbers.
   - On fail: either reject outright (→ `guardrail_rejected` terminal state) or feed back as a correction signal (once correction exists in Step 5).
2. **`fixtures/redteam_guard/`** — a **named deliverable**: injected dangerous queries (write attempts, drops, cartesian bombs) plus natural-language prompts that try to *induce* dangerous SQL (prompt-injection-style). Each labeled with expected guardrail verdict.
3. **`tests/`** for `guard.py` driven by the red-team fixture.

## Explicitly deferred to Step 6
**Table-scope enforcement** ("touches tables it shouldn't") needs a per-db allowed-tables list, which is schema metadata formalized in Step 6. Do **not** hardcode it provisionally here — let it arrive when its data source is real. Step 4's done-when must not silently require Step 6's metadata.

## Done when
Guardrails unit-test green against the red-team fixture, and you can state: "caught N% of red-team queries."

## Results log
Append the **red-team catch rate** (N% caught) with config + commit. This is a measured safety claim, directly relevant to the regulated-industry JDs.

## Pitfalls
- Resist LLM-judged safety checks — the whole point is determinism and testability.
- Cost check is heuristic-first; don't lean on EXPLAIN (SQLite has no cost-bearing EXPLAIN).
- Don't smuggle in table-scope enforcement; it's Step 6's.
