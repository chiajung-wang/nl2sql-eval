# Plan — Step 12: Metadata & schema-linking levers (from the AT&T BIRD paper)

**Phase:** Optimization — *attacking the table-selection frontier Step 11 named, with techniques from the field's #1 BIRD submission*
**Headline:** Step 11 converged on a single residual: the dominant failure across every model is **table selection** — and it ruled out schema-enrichment (#112), self-correction (#122), and a deterministic FK-soundness guardrail (#122). This step imports the levers that the #1-ranked BIRD submission used to beat exactly this problem, and measures each on our existing apparatus.

## Source

Shkapenyuk, Srivastava, Ghane, Johnson (AT&T CDO), **"Automatic Metadata Extraction for Text-to-SQL"**, arXiv:2505.19988v2, May 2025. The team held BIRD #1 (with and without oracle hints) across several windows in 2024–2025 using *metadata extraction* rather than a tuned generator. Their thesis matches ours from the other side: the hard part is understanding the database, not writing SQL — and they use **sqlglot**, the same parsing spine we do.

Their reported lifts on MiniDev (GPT-4o), for orientation (not our numbers):
- Profiling metadata > human SME metadata (61.2 vs 59.6, no hints).
- Their schema-linking 61.2 → 63.2; *perfect* schema-linking → 69.0 — so the headroom in table selection is real and large.

## Why this is the right next step

Step 11's plan ends at `issue-10` (#135, "explicit table pre-selection") with the frontier named but the *method* open, and `issue-9` (#134) labelling **why** the wrong table is chosen (`ambiguous_column` / `synonym_mismatch` / `domain_knowledge`). The paper supplies concrete, on-thesis methods for each label, and — critically — every one is measurable on apparatus we already built:

- **Retrieval recall vs gold tables** (PRD rule 7, recorded by `retrieve.py`) scores schema-linking directly.
- **The comparator** (`eval/compare.py`) is the result-set equivalence their majority-voting needs — we'd reuse it, not rebuild it.
- **The guard** (`guard.py`, deterministic sqlglot rules) is the exact shape of their "bad-SQL-construction" checks.
- **The diagnostic** (`eval/diagnose_bird.py`) re-runs to prove the targeted bucket moved.

## Evaluation protocol (inherited from Step 11)

Same dev/held-out discipline (`plan-step-11.md`): iterate every lever on the frozen dev slice, confirm the **targeted bucket shrank on dev** via the re-run diagnostic, and report the headline lift **once** on `step11-holdout` (or its widened successor from #133). Strict **and** BIRD set-semantics. Read small deltas against the ~0.05 sampling-noise floor. Every number → `RESULTS.md` with model, slice ID, prompt version, date, number, commit.

## The levers (ordered by leverage × alignment, substrate before consumers)

1. **`issue-1` (#138) — Schema linking by task-alignment (SQL-generation field harvesting).** The paper's contrarian core: LLMs are *bad* at directly naming relevant tables but *good* at generating SQL, so generate SQL across schema/profile variants and harvest the **fields the SQL references** — union = the linked schema. A direct A/B against `retrieve.py`'s lexical schema-RAG on **retrieval recall** and pass@1. This is the method `issue-10` (#135) left open. Highest leverage; flag the extra-generation cost.

2. **`issue-2` (#139) — Deterministic "bad-construction" checks as guard/correction signals.** AST-detectable anti-patterns that correlate with wrong answers: `min(f)`/ASC-order without `NOT NULL` (NULLs sort first), min/max via subquery instead of `ORDER BY … LIMIT`, field string-catenation. Pure sqlglot, pre-execution — our guardrail shape exactly; reject-or-feed-back, measured against a red-team-style fixture (rule 11).

3. **`issue-3` (#140) — Profiling-derived field metadata (precompute).** Deterministic column profile (null/distinct counts, min/max, value "shape", top-k samples, format sniff) → **cached, offline** LLM summary. Their result: it *beats* the supplied SME metadata. A retrieval-lift experiment (rule 7); summary is precomputed so determinism of guard/comparator is untouched. Largest build, largest accuracy headroom.

4. **`issue-4` (#141) — Literal→field matching (value index).** Extract literals from the question, find which columns actually *contain* those values, steer the `WHERE` to the right column. Targets the `ambiguous_column` root cause #134 labels. Deterministic index (LSH/sampled-value) — no LLM/regex for SQL semantics.

5. **`issue-5` (#142) — Candidate diversity + result-set majority voting.** Generate k candidates (seed + schema-field-order variation), execute, **majority-vote by result-set equivalence** (our comparator, repurposed from gold-scoring to selection). Directly informs the pass@1→pass@k gap (rule 6); an honest null is acceptable.

## Explicit non-goals (paper techniques we deliberately do *not* import)

- **Query-log mining for join paths / business logic** (paper §5). BIRD ships no query log; the technique is industrial-only. Cite it in the blog as evidence that undocumented join paths are real (they found 25%), but there is no buildable slice here. Stays a non-goal — consistent with §3 single-db, no cross-db routing.
- **SQL→text few-shot generation graded by human/LLM judgement** (paper §6). Using SQL→text as a *context* technique is fine; importing their **subjective grading** as a scorer is not — PRD bans LLM-as-primary-scorer (§7). Result-set comparison stays the scorer.

## Done when

At least one lever lands a **measured pass@1 lift that holds on held-out** (or an honest, explained null), with the diagnostic showing the **table-selection bucket shrank on dev** — every number in `RESULTS.md` with config + commit, dev and held-out both.

## Pitfalls

- **Cost is part of the result.** The schema-linking and majority-voting levers spend N× generations; report the lift *with* its token/latency price, as the Step-5 self-correction twin did.
- **Determinism boundary.** Profiling summaries and SQL→text are *offline precompute*; nothing LLM-derived may enter `guard.py` or `eval/compare.py` (§4/§7).
- **Same overfitting guard.** Confirm every lift on held-out before claiming it; never tune against held-out.
- **Prove the bucket moved, not just the headline** — a 50-q headline moves by luck.
