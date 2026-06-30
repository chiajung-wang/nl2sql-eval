# Issue 1 — Schema linking by task-alignment (SQL-generation field harvesting)

**Type:** AFK
**Phase:** Step 12 (Optimization) — *the method `issue-10`/#135 left open, supplied by the #1 BIRD submission*

## Parent

`docs/plans/step-12/plan-step-12.md` — source: Shkapenyuk et al., "Automatic Metadata Extraction for Text-to-SQL", arXiv:2505.19988v2, §3.

## Motivation

Step 11 ended with the frontier named (**table selection**) and `issue-10` (#135) framing an "explicit table pre-selection" lever — but left the *method* open. The paper supplies a specific, counter-intuitive one and reports it as the technique behind their #1 finish.

Their finding (paper §3, citing the *task-alignment* property): LLMs are **poor at directly naming relevant tables/columns** but **good at generating SQL**. So instead of asking "which tables are relevant?", they:

1. Generate an SQL query across **several schema/profile variants** (focused vs full schema × minimal vs maximal profile).
2. **Harvest the fields the generated SQL actually references** (sqlglot AST).
3. Take the **union** across variants as the linked schema — recall over precision ("better too many fields than too few").

This is fundamentally different from our `retrieve.py` lexical schema-RAG, which *scores and drops* tables to fit a budget. Task-alignment instead *lets the generator vote with its query*. The paper measures the gap that justifies the work: their schema-linking 61.2 → 63.2, but **perfect** schema-linking → 69.0 (no hints) — the table-selection headroom is large and unreached.

## What to build

A schema-linking strategy, selectable alongside the existing lexical schema-RAG, that:

- Runs the **generate** stage across a small set of schema variants (start with two: focused/lexical-RAG schema and full schema; extend to profile variants only if `issue-3` lands).
- Collects the **referenced fields** from each candidate via sqlglot AST (reuse `eval/diagnose_bird.py`'s existing field-extraction, don't fork it).
- Unions them into the schema handed to a **final** generate pass.
- Records the harvested table set on the state so the harness scores **retrieval recall vs the gold query's tables** (the apparatus already reports this — PRD rule 7).

Constraints (CLAUDE.md §3/§4/§7):
- **Import-shared pipeline** — this is a retrieval strategy the harness *and* demo select via config, never a fork. It threads through `retrieve.py` / `generate.py`; do not collapse stages.
- Field harvesting is **sqlglot-AST only** — no regex for SQL semantics.
- The intermediate SQL-generation passes are a *linking mechanism*, not extra answer candidates; keep them distinct from `issue-5`'s candidate voting (though they may share the multi-generation plumbing).
- **Cost is part of the result** — this spends N extra generations per question. Instrument and report token/latency cost alongside any lift, as the Step-5 twin did.

## Evaluation protocol

- A/B on the dev slice: lexical schema-RAG (current `retrieve.py`) vs task-alignment linking, on the **`accuracy` config** (#132) and the baseline. Report **retrieval recall** and **pass@1** (strict + BIRD set-semantics) for both.
- Re-run `diagnose_bird` and show the **table-selection bucket** (`missing_table` / `extra_table` / table-driven `spurious_join`, #122) moved on dev — the bucket is the target, not just the headline.
- Report the **per-question generation cost** (extra calls, tokens, wall-clock) as a first-class column — the lift is only meaningful against its price.
- Headline lift reported **once** on held-out (#133's widened slice if available, else `step11-holdout`).
- A "linking ceiling" reading: how close does harvested recall get to the **perfect-linking** upper bound (gold tables always present)? That gap is the residual the lever can't reach.

## Acceptance criteria

- [ ] A task-alignment schema-linking strategy selectable via config beside lexical schema-RAG; pipeline import-shared, stages not collapsed
- [ ] Field harvesting is sqlglot-AST based, reusing `diagnose_bird`'s extraction
- [ ] Retrieval recall **and** pass@1 (strict + BIRD) reported for both strategies on dev, baseline + `accuracy` config
- [ ] `diagnose_bird` re-run shows the table-selection bucket movement on dev
- [ ] Per-question extra-generation cost reported alongside the lift
- [ ] Headline lift (or honest null) reported once on held-out; recall-vs-perfect-linking ceiling documented
- [ ] Numbers in `RESULTS.md` with full config + commit
- [ ] `uv run pytest` green (linking logic unit-tested offline on recorded candidates); lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])** build + unit-test the harvesting/union offline on recorded candidate SQL first; refresh on a live run with an authorized key

## Out of scope

- Profiling-derived metadata variants (`issue-3`) — this issue uses the schema representations we already have; profile variants are an extension once #3 lands.
- The literal→field steering step the paper bundles into the same algorithm — split into `issue-4` to keep each lever independently measurable.
- Candidate selection / majority voting (`issue-5`) — the intermediate generations here are for *linking*, not answer voting.

## Blocked by

- Benefits from #133's wider slice for a less noisy recall delta; can iterate on dev meanwhile. Consumes #134's root-cause reading to predict whether linking (vs embeddings/few-shot) is the indicated lever.

---

## Tracking

**GitHub:** [#138](https://github.com/chiajung-wang/nl2sql-eval/issues/138) · labels `agent-ready`, `step-12`

**PR:** _pending_

**Step 12 set:** **#138 (this)** · #139 (bad-construction guards) · #140 (profiling metadata) · #141 (literal→field) · #142 (majority voting)
