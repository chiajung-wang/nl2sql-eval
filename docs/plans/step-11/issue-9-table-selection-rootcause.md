# Issue 9 — Root-cause decomposition of the table-selection cluster

**Type:** AFK
**Phase:** Step 11 follow-up (Optimization) — *one more cheap diagnostic pass before building a lever*

## Parent

`docs/plans/step-11/plan-step-11.md`

## Motivation (we know *which* bucket, not yet *why*)

Every Step 11 finding converges on the same conclusion: the dominant residual
failure, across **every** model, is **table selection** — wrong tables / wrong
join path. #112 proved schema enrichment can't fix it (the FKs are already in the
DDL). #122 sharpened it deterministically into `spurious_join` / `missing_table`
/ `extra_table` and showed the FK-unsound subset is a *minority* — the cluster is
dominated by **table selection**, a model-capability frontier no deterministic
guardrail reaches.

But #122 decomposed by **FK-soundness and direction** — *what kind* of mismatch.
It did **not** label **why the wrong table was chosen**. That root cause is what
decides which lever to build, and each points somewhere different:

- **Ambiguous column names** — the same column name lives on multiple tables, so
  the generator picks the wrong owner → points to **value-/column-linking**.
- **Synonym mismatch** — the question's word ≠ the table/column name
  (question says "customer," table is `client`) → points to **embeddings /
  semantic schema-linking**.
- **Genuine domain knowledge** — the mapping needs knowledge not in the schema
  → points to **few-shot exemplars** demonstrating the reasoning.

Building the wrong lever wastes a paid A/B in a regime where (on a 50-q slice)
the result lands inside the noise floor anyway. The harness makes this labeling
**cheap** — one more diagnostic pass earns the right to pick the lever the data
names, exactly as #111 did at the start of the step.

## What to build

A **diagnostic decomposition pass** over the table-selection failures
(`missing_table` / `extra_table`, plus the table-selection-driven
`spurious_join`s) that labels each by **root cause**:

- `ambiguous_column` — the chosen-vs-gold table difference is explained by a
  column name shared across both tables (detectable deterministically from the
  schema: column-name → owning-tables multimap intersected with the candidate's
  FROM/JOIN set).
- `synonym_mismatch` — the gold table's name/columns are lexically distant from
  the question tokens while the chosen table is closer (a lexical-overlap signal;
  string/token comparison, **no LLM judge for SQL semantics** — keep it a
  diagnostic heuristic, clearly labeled as such).
- `domain_knowledge` — residual: neither of the above explains the swap.

Constraints (CLAUDE.md §4/§7):
- The deterministic parts (column-ownership, FROM/JOIN extraction) are
  **sqlglot-AST + schema graph**, reusing `enrich.py`'s FK/table metadata and
  `diagnose_bird.py`'s existing decomposition — extend it, don't fork it.
- A lexical/semantic *labeling heuristic* is acceptable **for the diagnostic
  only** (it informs which lever to build); it must never enter the comparator
  or guard. State this boundary explicitly in the code.
- Output a per-root-cause count on the dev slice for both the **baseline** and
  the **`accuracy`** config, so the label distribution is model-checked, not
  read off one model (mirror #122's cross-model consistency check).

## Evaluation protocol

- This issue produces a **diagnostic distribution, not an accuracy number** — the
  deliverable is the per-root-cause breakdown with its method documented, plus a
  one-paragraph reading of *which lever the data points to* (the input to
  issue-10).
- Run on dev for baseline + `accuracy` config; record the breakdown in
  `RESULTS.md` (it's a measured artifact of the apparatus, like #122's
  decomposition), with full config + commit.
- Sanity-bound the heuristic: report how many `synonym_mismatch` labels survive a
  spot-check, so the label's reliability is stated, not assumed.

## Acceptance criteria

- [ ] `diagnose_bird` extended to tag table-selection failures by root cause
      (`ambiguous_column` / `synonym_mismatch` / `domain_knowledge`); deterministic
      parts are sqlglot-AST + schema-graph based, the lexical heuristic is
      diagnostic-only and labeled as such (no comparator/guard contamination)
- [ ] Per-root-cause distribution reported for **both** baseline and `accuracy`
      config on dev, with cross-model consistency noted
- [ ] A documented reading of which lever the dominant root cause points to —
      the explicit input to issue-10
- [ ] Breakdown + method recorded in `RESULTS.md` with full config + commit
- [ ] `uv run pytest` green (new diagnostic logic unit-tested on fixture
      failures); lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])**
      the failure set comes from paid runs; build + unit-test the tagging offline
      on recorded failures first, then refresh on a live run with an authorized key

## Out of scope

- Building the lever itself (issue-10 consumes this output).
- Any LLM-as-judge for root-cause labeling as a *primary* signal (PRD non-goal;
  the deterministic + heuristic diagnostic is the boundary).
- Re-opening schema enrichment (#112) or the FK-soundness corrector (#122) — both
  settled.

## Blocked by

- Benefits from issue-8's wider slice for a less noisy distribution, but can run
  on the current dev slice if issue-8 lags. Reuses #122's decomposition and
  `enrich.py`.

---

## Tracking

**GitHub:** [#134](https://github.com/chiajung-wang/nl2sql-eval/issues/134) · label `agent-ready`, `step-11`

**PR:** _pending_

**Step 11 follow-up set:** #121 · #122 · #132 (named configs) · #133 (wider
slice) · **#134 (this)** · #135 (explicit table pre-selection)
