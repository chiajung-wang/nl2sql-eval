# RESULTS

The committed running results log. **A step is not done until its number is
appended here** with the exact config that produced it: every reported number
must be traceable to its config and commit (CLAUDE.md §6, PRD §10).

Capture especially the **pass@1 → pass@k gap** (Step 5, what self-correction is
worth) and the **naive-baseline → schema-RAG retrieval lift** plus **retrieval
recall** (Step 6).

## Log

| Date | Step | Metric | Number | Model | Slice ID | Prompt version | Commit |
| ---- | ---- | ------ | ------ | ----- | -------- | -------------- | ------ |
| 2026-06-11 | 3 | pass@1 | 0.420 (21/50) | claude-sonnet-4-6 | step3-naive-schema-dump-baseline | generate/v2 | 5d9d8ae |
| 2026-06-12 | 4 | red-team catch rate | 1.000 (29/29) | — (deterministic gate) | redteam_guard | guard rules: read_only+dangerous_op+cost | e56fbcd |
| 2026-06-12 | 5 | pass@1→pass@3 | 0.420 (21/50) → 0.420 (21/50) [gap +0.000] | claude-sonnet-4-6 | step3-naive-schema-dump-baseline | generate/v3 | 7ae5bb5 |

**Step 4 — guardrail catch rate.** The deterministic, pre-execution guard gate
(`src/nl2sql/pipeline/guard.py`) caught **29/29 (100%)** of the dangerous queries
in the `fixtures/redteam_guard/` red-team set, with 43/43 verdicts matching
(every benign control allowed). Reproduce with `uv run python -m eval.redteam`.
The set spans write/DDL (incl. `REPLACE`-as-`Command` and CTE-wrapped writes),
dangerous ops (stacked statements, `ATTACH`/`DETACH`, `PRAGMA`, unmodeled
commands), cost/complexity (cartesian products, join explosion, unbounded
`SELECT *`), and **prompt-injection** attacks whose induced payloads the gate
rejects pre-execution. No LLM judge, no regex for SQL semantics — sqlglot ASTs
only. Table-scope enforcement is deferred to Step 6 (needs per-db metadata).

**Step 5 — pass@1 → pass@3 gap (what self-correction is worth).** Over the frozen BIRD slice, enabling the capped execution-error correction loop moves accuracy from **pass@1 0.420 (21/50)** to **pass@3 0.420 (21/50)** — a gap of **+0.000**. Of the **29** pass@1 failures, **0** were execution errors (the only kind the loop can feed back), **27** were wrong-answers (clean execution, wrong result), and **2** were guardrail rejections. The loop **never fired** — there were no execution errors to correct — so the gap is necessarily **0**, and the cost/latency delta is **exactly 0** (pass@1 is derived from this same run's first attempts, so with no retries the two views are identical — no second run, no sampling noise). The honest reading: on this slice the failures are **semantic, not syntactic** — recovering them needs better retrieval/generation (Step 6), not retry. This is exactly where the twin metric earns its keep: it proves self-correction adds no accuracy here rather than letting a headline pass@3 imply otherwise. pass@1 matches the Step-3 baseline (`generate/v3` renders byte-identical to v2 with correction off). Reproduce with `uv run python -m eval.eval_bird_twin`.
| 2026-06-13 | 6 | retrieval lift (pass@1) | 0.700 (28/40) → 0.575 (23/40) [lift -0.125] | claude-sonnet-4-6 | step6-large-schema-retrieval-lift | generate/v3 | ff342d7 |

**Step 6 — naive-dump → schema-RAG retrieval lift (large-schema slice).** On the frozen `step6-large-schema-retrieval-lift` slice, schema-RAG moves pass@1 from **0.700 (28/40)** to **0.575 (23/40)** — a lift of **-0.125** — with retrieval recall **0.942**. On these dbs (≤14 tables) the whole schema still **fits** the model's context, so the naive dump already hands the model every table, while schema-RAG — whose job is to *drop* tables to fit a budget — occasionally drops a **needed** one. Recall **0.942** means ~5.8% of the gold tables were missed, and those become wrong answers: the recall metric diagnoses the loss directly. Retrieval is **not free** — its lift is where the schema *overflows*; here it does not, so retrieval can only lose information. This is the twin of Step 5's finding: measurement over a hoped-for headline. Reproduce with `uv run python -m eval.eval_bird_rag`.
| 2026-06-15 | 6 | budget-crossover retrieval lift | max gap +0.100 @512t, converges @4096t (RAG-select vs naive-truncate, pass@1) | claude-sonnet-4-6 | step6-large-schema-retrieval-lift | generate/v3 | 1c2f5eb |

**Step 6 follow-up (#75) — schema-token-budget retrieval crossover.** BIRD has no schema that overflows a modern context window (largest ~1.8K tokens), so this is a **controlled experiment**, not a natural-overflow claim: under a configured schema-token *budget* (a cost/latency policy), is it better to **truncate** the schema or to **retrieve** the relevant tables? On the frozen `step6-large-schema-retrieval-lift` slice, the modes **converge at 4096t** (selection divergence 0 — every schema fits, so both send the generator identical prompts). The residual +0.050 there is therefore **sampling noise**, not retrieval: generation runs at non-zero temperature, so two independent runs on the *same* prompt differ by ~0.050 (2/40 questions). Read the tight-budget gaps against that floor: the pass@1 advantage peaks at **512t (+0.100)** but is modest relative to it, so on this 40-question slice the gap is suggestive, not conclusive. RAG recall climbs 0.450→1.000 with the budget — the robust signal: more budget lets retrieval cover more of the gold tables, while truncation gets no such targeting. This is the honest other half of the Step-6 finding: where the full schema fits the budget the two modes are identical; where it does not, retrieval keeps the *right* tables and truncation cuts blindly — the recall gap is real and monotone, the pass@1 gap real but small against sampling noise. With today's context windows that budget is a policy choice, not a hard limit.

| schema-token budget | naive-truncate pass@1 | RAG-select pass@1 | gap | RAG recall | selection divergence |
| --- | --- | --- | --- | --- | --- |
| 256 | 0.475 (19/40) | 0.500 (20/40) | +0.025 | 0.450 | 0.750 |
| 512 | 0.525 (21/40) | 0.625 (25/40) | +0.100 | 0.569 | 0.750 |
| 1024 | 0.525 (21/40) | 0.600 (24/40) | +0.075 | 0.752 | 0.650 |
| 2048 | 0.575 (23/40) | 0.650 (26/40) | +0.075 | 0.900 | 0.350 |
| 4096 | 0.625 (25/40) | 0.675 (27/40) | +0.050 | 1.000 | 0.000 |

Reproduce with `uv run python -m eval.eval_bird_budget`.
