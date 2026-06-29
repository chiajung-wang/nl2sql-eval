# Issue 10 — Explicit table pre-selection (schema-linking step)

**Type:** AFK
**Phase:** Step 11 follow-up (Optimization) — *attack the real frontier: table selection; research lever, may yield an honest null*

## Parent

`docs/plans/step-11/plan-step-11.md`

## Motivation (where the headroom actually is)

Every diagnostic in Step 11 lands in the same place: the dominant failure across
**every** model is **table selection**, and the prior levers ruled out the easy
explanations — it isn't retrieval (#112: the FKs and tables are already in the
DDL), it isn't self-correction (a wrong join runs without error, so nothing feeds
back — #122), and it isn't a deterministic guardrail (#122: the FK-unsound subset
is a minority). #122's honest conclusion was "model-capability frontier, and the
model swap is what moved it." This issue tests the remaining *non-model* lever
the frontier leaves open: **make the model reason about table choice explicitly,
before it writes SQL.**

This is distinct from schema-RAG, which *drops* tables to fit a budget. Here the
schemas already fit — so the lever is **forcing an explicit "which tables answer
this question" reasoning step** and committing the generator to that set, rather
than letting table choice be an implicit side effect of one-shot SQL generation.

## What to build (candidate sub-experiments — sequence per issue-9's root cause)

issue-9 names the dominant root cause; let it order these.

1. **Explicit table pre-selection as a pipeline step** — a cheap first call
   (small LLM, or embedding ranking) that ranks candidate tables for the
   question; the generate step then receives that committed set as the working
   schema. A new stage respecting **one-stage-per-module** (CLAUDE.md §3) —
   slots before `generate` (e.g. between `retrieve` and `generate`); the
   pipeline stays import-shared (no demo fork). A/B on dev with
   `missing_table`/`extra_table` bucket movement.
2. **Schema-aware join few-shot** — exemplars that specifically demonstrate
   *multi-table join reasoning on similar schemas* (choosing the right join
   owner, chaining a bridge table). This targets the actual remaining bucket,
   unlike #113's precision exemplars (closed because precision buckets were
   already cleared). **Leakage guard:** exemplars from **outside every eval
   slice** (same rule as #113/#122). Prompts externalized in `prompts/`.
3. **Self-consistency over table sets** — sample k generations; where they
   **disagree on the FROM/JOIN set**, that disagreement is a strong signal of a
   hard question. Useful two ways: as a possible accuracy lever (majority-vote
   the table set) and — independent of any accuracy lift — as a **confidence
   diagnostic** the apparatus can surface. The disagreement signal is computed
   deterministically (sqlglot AST over the k candidates' FROM/JOIN sets).

## Evaluation protocol (non-negotiable)

- Follow the **dev/held-out** protocol (`plan-step-11.md`), and prefer issue-8's
  **wider slice** for dev iteration — these are marginal-effect levers, the exact
  regime a 50-q slice can't resolve (the noise-floor caveat that deferred #122).
  Confirm any lift **once** on `step11-holdout`; report pass@1 **strict and BIRD
  set-semantics**, dev and held-out.
- The claim is the **held-out** lift *and* the diagnostic showing
  `missing_table`/`extra_table` shrank on dev — not a bare headline.
- **Leakage rule** for any few-shot: exemplars from **outside all eval slices**.
- An **honest, explained null is an acceptable outcome** (as #112 and #122 were).
  For sub-experiment 3, a confidence-diagnostic that *correlates with
  correctness* is a shippable apparatus result even with no accuracy lift.
- Watch **added cost/latency**: a pre-selection call or k-sampling multiplies
  spend — report the accuracy-per-dollar trade, not just pass@1.

## Acceptance criteria

- [ ] At least one sub-experiment implemented and A/B'd on dev (preferably the
      wider slice) with **table-selection bucket movement** from the re-run
      diagnostic
- [ ] Any new pipeline stage respects module boundaries + import-sharing (no demo
      fork); any disagreement/soundness signal is **sqlglot-AST based**; any
      few-shot keeps prompts in `prompts/` with exemplars outside every slice
- [ ] Held-out lift confirmed on `step11-holdout` **or** an honest null with
      bucket evidence; dev + held-out numbers in `RESULTS.md` (strict + BIRD,
      full config + commit), with the added cost/latency reported
- [ ] `uv run pytest` green; lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])**
      the A/B runs are paid (and pre-selection/k-sampling multiply the spend);
      prove the apparatus offline first, then run with an authorized key/budget

## Out of scope

- Cross-db routing or table-scoping across databases (PRD non-goal).
- LLM-as-judge as the *primary* scorer or for join correctness (comparator/guard
  stay deterministic).
- Re-litigating schema enrichment (#112) or FK-soundness correction (#122).
- Repinning the default model (issue-7 handles config selection).

## Blocked by

- **issue-9** (root-cause decomposition) sequences the sub-experiments. Strongly
  benefits from **issue-8** (wider slice) so the marginal effect is measurable —
  without it, a null here is "inconclusive," not "decided." Reuses `enrich.py`'s
  schema graph and `diagnose_bird.py`.

---

## Tracking

**GitHub:** [#135](https://github.com/chiajung-wang/nl2sql-eval/issues/135) · label `agent-ready`, `step-11`

**PR:** _pending_

**Step 11 follow-up set:** #121 · #122 · #132 (named configs) · #133 (wider
slice) · #134 (table-selection root cause) · **#135 (this)**
