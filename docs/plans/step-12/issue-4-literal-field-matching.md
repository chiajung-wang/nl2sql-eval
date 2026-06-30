# Issue 4 — Literal→field matching (value index) for column linking

**Type:** AFK
**Phase:** Step 12 (Optimization) — *targets the `ambiguous_column` root cause #134 labels*

## Parent

`docs/plans/step-12/plan-step-12.md` — source: Shkapenyuk et al., arXiv:2505.19988v2, §3 (the schema-linking preprocessing + literal-matching loop).

## Motivation

A recurring wrong-answer class is **right value, wrong column**: the generator constrains a literal (`'Fresno County Office of Education'`) against a plausible-but-wrong field. The paper handles this deterministically — it indexes sampled field values, then, after generating SQL, **checks whether each literal in the query actually occurs in the field it's constrained against**; if not, it finds which fields *do* contain the literal and asks the model to rephrase using one of them. Their worked example flips a `County Name` constraint to the correct `District` field this way.

This targets exactly the `ambiguous_column` root cause that Step 11's `issue-9` (#134) labels — where the same/similar literal is valid against multiple columns and the generator picks the wrong owner. It is deterministic (an index lookup + a steering prompt), so it fits our "no LLM/regex for SQL semantics" rule: the *matching* is mechanical; only the *rephrase* is LLM, and that rides the existing `correct.py` loop.

## What to build

- A **value index** over sampled distinct values per column (the paper uses an LSH-on-shingles index for approximate match on a moderate sample — N≈10k — explicitly *not* indexing every value, which doesn't scale). Reuse `issue-3`'s profiling pass for the value sample if it has landed; otherwise sample directly.
- A post-generation step that, per literal in the candidate SQL: looks up which columns contain it; if the literal's constrained column is **not** among them, surfaces the candidate columns and feeds a **steering correction** ("this literal occurs in fields X/Y/Z; revise to constrain one of them").
- Wire as a correction signal through `correct.py` within the **capped retry budget** (§5).

Constraints (CLAUDE.md §3/§4/§7):
- Literal extraction from the candidate is **sqlglot-AST**; the index lookup is mechanical; **no LLM/regex** for the SQL-semantic decision. The rephrase prompt is the only LLM touch, owned by `correct.py`.
- Index is a deterministic, sampled artifact — moderate sample, not full-column (scalability is the paper's explicit caution).
- Import-shared; the index builds the same way for harness and demo.

## Evaluation protocol

- A/B on dev with vs without literal-steering, `accuracy` config; pass@1 (strict + BIRD).
- Re-run `diagnose_bird`; expect movement specifically in the `ambiguous_column`-driven `where_mismatch` subset #134 isolates — show *that* subset moved, the targeted claim.
- Report the **steering trigger rate** (how often a literal was off-column) and **recovery rate** (how often the rephrase fixed it) + added retries — the Step-5-twin pattern: value with its price.
- Report the **false-steer rate**: cases where the literal was legitimately on its column and the index disagreed (sampling miss) — the precision cost of an approximate index.
- Held-out headline (or null) once.

## Acceptance criteria

- [ ] Deterministic sampled value index over columns (reusing `issue-3`'s profiling sample if present); moderate sample, not full-column
- [ ] Post-generation literal-on-column check (sqlglot-AST literal extraction + mechanical lookup), feeding a steering correction via `correct.py` within the retry budget
- [ ] No LLM/regex in the matching decision; LLM confined to the rephrase prompt
- [ ] Dev A/B pass@1 (strict + BIRD); `diagnose_bird` shows the `ambiguous_column`/`where_mismatch` subset moved
- [ ] Trigger rate, recovery rate, false-steer rate, and added-retry cost reported
- [ ] Held-out headline (or null) once; numbers in `RESULTS.md` with full config + commit
- [ ] `uv run pytest` green (index + literal-check unit-tested offline on recorded candidates); lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])** index build + literal check are offline/deterministic and testable now; live A/B refreshes on an authorized key

## Out of scope

- Semantic (embedding) field matching — that's the `synonym_mismatch` lever #134 points elsewhere; this issue is the *literal/value* path only.
- Building the full task-alignment linker (`issue-1`) — this is the narrower literal-steering step the paper bundles into it, split out for independent measurement.

## Blocked by

- Softly depends on `issue-3`'s profiling pass for the value sample (can sample independently if #3 lags). Best sequenced after #134's root-cause labels confirm `ambiguous_column` is a material share.

---

## Tracking

**GitHub:** [#141](https://github.com/chiajung-wang/nl2sql-eval/issues/141) · labels `agent-ready`, `step-12`

**PR:** _pending_

**Step 12 set:** #138 (task-alignment linking) · #139 (bad-construction guards) · #140 (profiling metadata) · **#141 (this)** · #142 (majority voting)
