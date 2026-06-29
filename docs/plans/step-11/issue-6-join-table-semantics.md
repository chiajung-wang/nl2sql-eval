# Issue 6 — Join/table-semantics lever (the residual bottleneck)

**Type:** AFK
**Phase:** Step 11 follow-up (Optimization) — *the hard NL→SQL core; research lever, may yield an honest null*

## Parent

`docs/plans/step-11/plan-step-11.md`

## Motivation (what every prior lever left behind)

After the model swap (#117) and with few-shot precision shelved (#113), the dominant residual failures are **wrong joins and wrong tables**. On the `gemini-3.1-flash-lite` dev baseline (#117 follow-up): `join_mismatch` 11 + `table_mismatch` 10 = **21 of 27 genuine failures**; the precision buckets are near-zero (`projection` 2, `where` 1).

Crucially, #112 already proved this is join **semantics**, not join **discovery**: enriching the schema with explicit FK paths did *not* lift the headline, because the foreign keys are *already in the DDL* — the model knows the tables and still composes them wrong. So the lever is not "show more schema"; it is "constrain or correct the join composition." This is the genuine NL→SQL frontier and the honest hard part — frame it as a hypothesis test that may return a measured null.

## What to build (candidate sub-experiments — pick/sequence during implementation)

1. **Join-path-focused few-shot** — generic exemplars (made-up tables, **outside every eval slice** — same leakage guard as #113) that demonstrate *multi-table join composition*: choosing the correct join key, chaining through a bridge table, not over-joining. Distinct from v4's precision exemplars (which targeted projection/distinct). A/B on dev with `join_mismatch`/`table_mismatch` bucket movement.
2. **Deterministic join-soundness correction signal** — extend self-correction to a *wrong-answer* class it currently cannot catch (a bad join runs without error, so no error feeds back). Using sqlglot AST + the FK graph already built in `eval/datasets/bird/enrich.py`, detect when a generated query **joins two tables with no FK relationship** (or on a non-key column) and feed that back as a correction hint. **Deterministic, AST-based — no regex/LLM for SQL semantics** (CLAUDE.md §4/§7); fits the existing guard/correction pattern.
3. **(Stretch) Table-scope hinting from retrieval** — surface the retrieval-recall tables as a soft hint so the generator stays within the relevant table set. Only if 1–2 underperform.

## Evaluation protocol (non-negotiable)

- Follow the **dev/held-out** protocol (`plan-step-11.md`): tune/measure bucket movement on dev (`step3-naive-schema-dump-baseline`), confirm any lift **once** on `step11-holdout`; report pass@1 **strict and BIRD set-semantics**, dev and held-out.
- The claim is the **held-out** lift *and* the diagnostic showing `join_mismatch`/`table_mismatch` shrank on dev — not a bare headline (sampling noise ~0.05 on 50 q).
- **Leakage rule** for any few-shot: exemplars from **outside all eval slices**.
- An honest, explained **null is an acceptable outcome** (as #112 was) — record it.

## Acceptance criteria

- [ ] At least one sub-experiment implemented and A/B'd on dev with **join/table bucket movement** from the re-run diagnostic
- [ ] Any deterministic check is **sqlglot-AST based** (no regex/LLM for SQL semantics); any few-shot keeps prompts externalized in `prompts/` and exemplars outside every slice
- [ ] Held-out lift confirmed on `step11-holdout` **or** an honest null with bucket evidence; dev + held-out numbers in `RESULTS.md` with full config + commit
- [ ] `uv run pytest` green; lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])** the A/B runs are paid; prove the apparatus offline first, then run with an authorized key/budget

## Out of scope

- Cross-db routing (PRD non-goal).
- LLM-as-judge for join correctness (the comparator/guard stay deterministic).
- Re-litigating schema enrichment (#112 settled the discovery-vs-semantics question).

## Blocked by

- None hard. Reuses `enrich.py`'s FK graph (#112) for sub-experiment 2. Independent of [#121](https://github.com/chiajung-wang/nl2sql-eval/issues/121), though the robust extractor should land first so reasoning-class generators can be measured cleanly here.

---

## Tracking

**GitHub:** [#122](https://github.com/chiajung-wang/nl2sql-eval/issues/122) · label `agent-ready`, `step-11`

**PR:** _pending_

**Step 11 follow-up set:** [#121](https://github.com/chiajung-wang/nl2sql-eval/issues/121) (robust `_extract_sql`) · [#122](https://github.com/chiajung-wang/nl2sql-eval/issues/122) (this)
