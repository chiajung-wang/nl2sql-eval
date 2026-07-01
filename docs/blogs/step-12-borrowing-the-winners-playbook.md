---
title: "Step 12 — Borrowing the Winner's Playbook"
subtitle: "Step 11 named the frontier — table selection on multi-table joins — and left the method open. The #1 BIRD submission supplies five specific ones. This step imports all five as deterministic machinery, and the striking part is that every one of them plugs into a piece of apparatus we had already built: the retrieval-recall metric, the guardrail shape, the comparator. Built as deterministic machinery, proven offline — then run live once a key was authorized, and the verdict came back the same table-selection frontier Step 11 named."
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 12
date: 2026-07-01
author: Chia-Jung Wang
tags: [llm, nl2sql, evaluation, optimization, schema-linking, data-profiling, majority-voting, measurement, negative-results, replication]
---

# Step 12 — Borrowing the Winner's Playbook

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness and the apparatus around it are the *product*. Step 11 pointed the finished
> apparatus back at the workload and found a wall: the residual failures are **table
> selection on multi-table joins**, a model-capability frontier that this slice's prompt
> and deterministic levers couldn't reach. It named the frontier and left the *method*
> open. Step 12 goes looking for methods that have actually cleared it — the techniques
> behind a **#1 BIRD submission** (Shkapenyuk et al., arXiv:2505.19988v2) — and imports
> five of them. The surprise isn't the techniques. It's that every single one snaps onto
> a component the earlier steps already built and proved: schema linking is scored by the
> Step-6 recall metric, the soundness checks are the Step-4 guardrail shape, and majority
> voting *is* the Step-2 comparator with its inputs swapped. The apparatus turned out to
> be the substrate the borrowed playbook runs on.

Every earlier step built a piece of apparatus and proved it on demand; Step 11 consumed
the whole thing for optimization and hit a model-capability wall. The obvious next move is
a stronger generator — but before reaching for one, there's a more interesting question:
the people who *won* this benchmark, what did they actually do? Their paper is unusually
concrete. It's not "we used a bigger model"; it's a pipeline of specific, mostly
**deterministic** tricks. This step is a faithful import of that pipeline, one issue per
lever, filed as Step-12 follow-ups (#138–#142).

One process note up front, because it shaped the step. This project's discipline is that
**no number ships without a live run behind it**. Step 12 was built and merged *before* an
API key was authorized, so it first shipped as **machinery and offline, deterministic
proofs**, with every accuracy A/B recorded in `RESULTS.md` as explicitly pending — never a
fabricated lift. That sequencing was the point: for four of these five levers the
deterministic core *is* the hard part and *is* fully provable offline, and — per the lesson
Steps 5 and 11 kept teaching — several were likely honest nulls on a strong generator anyway.
When the key arrived, the A/Bs ran (below), and the prediction held: the machinery does
exactly what it claims, and the borrowed playbook moves this slice's strong-model accuracy by
nothing that clears the noise floor. The deterministic proofs and the live nulls are *both*
the finding.

---

## #138 — Schema linking by task-alignment: let the generator vote with its query

The paper's contrarian opening: LLMs are **poor at directly naming relevant tables** (a
task they were never trained on) but **good at generating SQL**. So instead of asking
"which tables are relevant?", ask the model to *write SQL* against a couple of schema
variants and **harvest the tables that SQL actually references** — the union is the linked
schema. Recall over precision: better too many tables than too few.

This is the exact inverse of our lexical schema-RAG, which *scores and drops* tables to fit
a budget — and it plugs into apparatus we already own. The harvested table set lands on
`state.retrieved_tables`, the same field the **Step-6 retrieval-recall metric** reads, so
the linker's coverage is measured against the gold query's tables *identically* to how RAG's
is. The whole harvesting core is deterministic sqlglot-AST table extraction (an alias, a
column named like a table, or the word `from` in a string literal can't fool it), so it is
trivially testable with a fake generator: 17 offline cases prove the harvest, the
declaration-order union, that a hallucinated table is dropped, and that an all-empty harvest
degrades to lexical RAG rather than starving the generator. The review caught one real thing
— a typo'd strategy name silently ran the baseline, which would misattribute a measured A/B —
now a hard error. Live (below), the linker did harvest better recall (0.942 → 0.958) — but on a
strong model with already-high recall, that bought no accuracy; the mechanism works, the headroom
wasn't there.

---

## #139 — Deterministic bad-construction checks: the guardrail shape, as a correction

The submission runs a set of **deterministic, AST-detectable "bad SQL construction" checks**
after generation and gates candidates on them. These aren't stylistic — each correlates with
a *wrong answer*: a `NULL` sorts before all values, so `ORDER BY f ASC LIMIT 1` or `min(f)`
without a `NOT NULL` guard silently returns a NULL-driven wrong row; a min/max computed by a
scalar subquery where `ORDER BY … LIMIT 1` is idiomatic; a projection that string-concatenates
distinct fields the question wants separate.

This is *exactly* our Step-4 guardrail shape — deterministic sqlglot checks, no regex for SQL
semantics, no LLM judge — with one deliberate difference in contract. The guard **rejects**
(a terminal `guardrail_rejected`); a soundness hit is a **correction signal**. With retry
budget left, the reason feeds back to `generate`; with the budget spent, the candidate
executes anyway. A soundness heuristic must never *lose* a run, so a false positive costs at
most a wasted retry, never a dropped answer. And because it's the guardrail shape, it's
measured the guardrail way — against a fixture with positives and near-miss negatives:

| `fixtures/soundness/` | catch rate | false-positive rate |
|---|---|---|
| null-ordering + minmax-subquery + field-catenation | **1.000 (9/9)** | **0.000 (0/12)** |

That fixture number is the durable, offline deliverable. It also carries an honest caveat the
review surfaced: SQL `MIN` *ignores* NULLs, so the bare-`min(f)` positives encode the paper's
hazard claim (which holds on the BIRD questions whose gold query itself adds `IS NOT NULL`),
not an objective SQL truth — so the `9/9` is a catch rate against a spec-inherited label for a
few of the nine, and the live A/B is what would adjudicate its real worth. On the flash-class
generators the precision buckets are already near-zero (Step 11), so that live lift may be
~0 — an acceptable, expected outcome. The fixture proof is the result.

---

## #140 — Profiling beats supplied metadata: the paper's headline, built to the boundary

The paper's most surprising result, and its biggest build: **profiling the data beats
human-supplied metadata** (MiniDev, no hints: profiling 61.2 vs supplied 59.6; fused best
63.2). Cryptic schemas hide format the data exposes — that `CDSCode` is a 14-char
County-District-School id, that `Academic Year` is `'YYYY-YYYY'`, that an undocumented column
is JSON. Step 11 had ruled out the *cheaper* metadata move (FK enrichment was a null — the FKs
were already in the DDL) but never tried **data-derived** field descriptions.

The build splits cleanly along the project's determinism boundary. A **deterministic profiler**
records each column's shape — counts, NULL fraction, distinct, character class, common prefix,
length range, top-k — over the SQLAlchemy executor, and a **mechanical** renderer turns that
into English. No LLM in either; and offline they already recover the paper's own examples:

```
Column "CDSCode" (TEXT). No NULLs across N rows. All values distinct (unique).
Values are exactly 14 characters long, all digits, always beginning with "0110017000000".
```

Only the *summarization* into a short (for linking) and long (for generation) description
touches a model, and that is **offline precompute**, frozen to a version-controlled
`profiles/<db>.json` the live pipeline only reads — same discipline as `prompts/`. The
load-bearing rule: these descriptions are **generate-prompt content only**; they never reach
`guard.py` or `eval/compare.py`, which stay deterministic and data-independent so scoring is
untouched. The review found the second half of that boundary I'd left implicit — the profiler
embedded *raw values* into descriptions, harmless on public BIRD but a raw-PII leak on the
payments path — now the profiler is **PII-aware**: a redaction-policy column profiles
shape-only, never its values. A `METADATA_SOURCE` axis (supplied / profiling / fused) selects
the source, wired into the eval index-build so it's active in a real run. The three-way A/B is
the headline A/B — which, run live (below), came back *against* the paper: profiling underperformed
supplied on this slice.

---

## #141 — Literal→field steering: right value, wrong column

A recurring wrong-answer class — the `ambiguous_column` cause Step 11's diagnostic labels — is
a literal constrained against a plausible-but-wrong field. Ask for the id of *"Fresno County
Office of Education"* and the model writes `WHERE CountyName = '…'`, but that string lives in
`District`; the query runs clean and returns the wrong rows. The paper fixes it
deterministically: index sampled field values, check whether each literal actually occurs in
the column it's bound to, and if not, name the columns that *do* hold it and ask the model to
rephrase — flipping a `County Name` constraint to the correct `District`.

Every piece here is a reuse. A **sampled value index** (moderate sample, not full-column — the
paper's own scalability caution; and PII columns never indexed, inheriting #140's boundary)
maps a value to the columns that hold it. The literal extraction is **sqlglot-AST** — never a
regex — and the on-column decision is a mechanical set membership; only the *rephrase* is a
model call, and it rides the same `correct.py` correction loop the soundness checks use. It
fires **only when confident**: the constrained column was sampled and lacks the literal *while
another column has it*, so a sampling miss can't spuriously steer. Twenty offline tests prove
it recovers the paper's `CountyName`→`District` flip and its alias-qualified form, stays silent
on on-column and unknown literals, and regenerates through the graph. Live (below), on this slice
it **triggered zero times** — the strong model produced no off-column literal the sampled index
caught — so its live contribution was a clean ±0. The mechanism is proven; the slice gave it
nothing to catch.

---

## #142 — Majority voting: the comparator, pointed sideways

The last lever is the one that made the apparatus-as-substrate point undeniable. The submission
generates several candidates and selects one by **majority vote on executed result-sets**. And
result-set equivalence is *precisely* what we built in **Step 2**: the comparator, with its
canonicalization and BIRD set-semantics, that has scored every number in this series. Voting is
that comparator applied to **candidate selection** instead of **gold scoring** — same core,
inputs swapped. No new equivalence logic, no string-match, no LLM judge.

So `eval/voting.py` groups k candidates into equivalence classes via
`compare(a, b, "SELECT 1").correct` (a gold-less, order-insignificant sentinel → "convert
results to sets"), picks the largest, and breaks a tie or no-majority **deterministically by
earliest index** — the paper picks randomly; reproducibility (§9) wants a fixed rule. The
scoring boundary is untouched: voting only *chooses* which candidate's raw verified result the
harness scores, upstream of redaction. Candidate diversity is the paper's deterministic
schema-field-order shuffle (seed variation, its second lever, only bites a stochastic model, so
it's live-only). Twenty-two offline tests prove the vote, the tiebreak, errored-candidate
exclusion, and — the reuse made explicit — that two results agree under the comparator's
*order-insensitive and float-tolerance* rules, not by string match.

And here the honest-null framing from Step 5 is not a hedge but the *expected* result: a strong
generator's candidates mostly agree, so the vote is a no-op (+0.000). The `agreement_distribution`
(unanimous / majority / no-majority) is the diagnostic that explains the gap. Live (below), the
strong model was unanimous on 32 of 40 questions — the vote a no-op — and recovered exactly one
(+0.025) from the uncertain remainder; the weak generator was *more* diverse (25 unanimous) yet
netted +0.000, because its majority wasn't reliably the correct answer. The selector works; the
disagreements just didn't resolve to accuracy on this slice.

---

## The scoreboard: machinery shipped, offline-proven — then run

The A/Bs were deferred only until a key existed. It does now, so the levers ran live on the
`accuracy` config (`gemini-3.5-flash`) over the frozen 40-question large-schema slice, and — the
weak-generator arms — on `kimi-k2.7-code`. Total spend ≈ **$9–10**.

| # | Lever | Reuses | Offline proof | Live result (strong model) |
|---|---|---|---|---|
| 138 | task-alignment schema linking | Step-6 recall metric | 17 tests; harvest/union/degrade | recall **+0.016**, pass@1 **−0.075** |
| 139 | bad-construction soundness checks | Step-4 guardrail shape | catch 1.000 / FP 0.000 (fixture) | 4 flags / 2 retries, **±0** |
| 140 | profiling-derived metadata | SQLAlchemy executor; PII boundary | 26 tests; recovers paper's examples | supplied 0.675 → **fused 0.625 → profiling 0.575** |
| 141 | literal→field steering | value index; `correct.py` loop | 20 tests; recovers County→District | **0 triggers**, ±0 |
| 142 | result-set majority voting | **Step-2 comparator** | 22 tests; comparator-rule reuse | 0.625 → **0.650** (+0.025); 32/7/1 agreement |

Reproduce any offline proof directly:

```bash
uv run pytest tests/test_schema_linking.py tests/test_soundness.py \
              tests/test_profiling.py tests/test_literal_field.py tests/test_voting.py
```

---

## The verdict: the apparatus adjudicated the borrowed playbook — to nulls

The baseline lexical RAG scored **pass@1 0.675** with retrieval recall 0.942. Against it, over the
40-question large-schema slice with the strong generator, **not one of the five borrowed levers
cleared the noise floor** (per-question SE ≈ 0.077):

- **#138 linking** did exactly what the mechanism promised — it *harvested better table coverage*
  (recall 0.942 → 0.958) — but that bought *nothing*, and cost 0.075 pass@1 and 3× the generations.
  The strong model already had high recall, so there was no table-selection headroom to capture;
  the recall-over-precision wider schema just added noise. The paper's lever pays where table
  selection is the bottleneck, and on this model it isn't.
- **#139 soundness / #141 literal-steer** fired at low rates and fixed nothing: soundness flagged 4
  candidates and forced 2 regenerations for a net **±0**; literal-steering **never triggered** (the
  model produced no off-column literal the sampled index caught). Self-correction fired **zero**
  retries — no execution errors on the strong model, exactly the Step-5 result, replayed.
- **#142 voting** is the one with a legible story. The vote-agreement distribution — **32 of 40
  questions unanimous**, 7 with a majority, 1 with none — *is* the finding: a consistent strong
  model mostly agrees with itself, so the vote is a no-op, and the small **+0.025** (one recovered)
  came entirely from the handful of uncertain questions. The honest null Step 5 taught to expect,
  now quantified by the diagnostic that explains it.
- **#140 profiling** produced the most interesting result, because it *diverges from the paper*.
  With all 613 columns of the slice's databases profiled and LLM-summarized live, the three-way
  came out **supplied 0.675 → fused 0.625 → profiling-only 0.575** — a monotonic *decline* with
  more injected profiling content, the opposite of the paper's *profiling > supplied* (61.2 > 59.6
  on GPT-4o/MiniDev). The descriptions are correct and useful (`budget.category` summarized to its
  exact five-value enum — the paper's enum-exposure thesis, live), but on a strong model the
  verbose long descriptions *distract and dilute* rather than clarify — the same mechanism Step 11's
  #112 found when sample-row enrichment hurt. Within ~1 SE, so suggestive not conclusive, but
  directionally clean and mechanistically plausible.

The weak generator (`kimi-k2.7-code`) didn't rescue any of them: voting stayed **+0.000** (more
diverse — 25 unanimous vs the strong model's 32 — but its *majority wasn't reliably the correct
answer*), and soundness went slightly negative (the retries regenerated as many right answers into
wrong ones as the reverse). Even kimi wrote zero execution errors on this slice, so self-correction
was inert here too — the malformed-SQL rate the correction loop feeds on is slice-dependent, and
this large-schema slice doesn't produce it.

The synthesis is the same one Step 11 reached, now stress-tested against a *#1 submission's*
playbook: this slice's residual failures are a **table/join-selection model-capability frontier**,
and neither our own deterministic levers nor the borrowed ones move it on a strong model. That is
not a disappointing result — it is the apparatus doing its job. It adjudicated five imported
techniques exactly as it adjudicated our own: honestly, mostly to nulls, with the one legible
positive (voting's +0.025) explained by its own diagnostic rather than asserted.

---

## What we refused to do

- **Fabricate the accuracy numbers — or bury the divergence.** The whole series' credibility is
  that a number names a live run, a slice, and a commit. Before the key we shipped the machinery
  and marked every A/B pending; after it, we reported what the runs actually said — including that
  **profiling *underperformed* supplied metadata on our slice, the opposite of the paper we borrowed
  it from.** An independent replication that diverges is a result, not an embarrassment to smooth over.
- **Rebuild the comparator for voting.** Result-set equivalence already exists, proven against
  its golden fixture; voting *reuses* it read-only. A second equivalence implementation would be
  a second source of truth and a place for drift.
- **Let profiling leak raw values.** The determinism boundary (descriptions never reach the
  guard or comparator) came for free; the PII half (never persist or render a redaction-policy
  column's raw values) came from the review, and it's enforced structurally, not by prose.
- **Let a typo run the baseline silently.** An unrecognized schema-link strategy now raises
  instead of quietly falling back to lexical RAG — because a misattributed A/B is worse than a
  crash.

---

## What's next

Step 11 found the wall; Step 12 imported the demolition tools, proved they're built correctly and
to the project's boundaries, and then — when the key arrived — ran them and reported that the wall
held. Five techniques from a #1 submission, and on a strong model over this slice the best of them
recovered a single question by luck of an uncertain vote; the paper's headline lever went the wrong
way. The residual failures remain what Step 11 named them: table and join selection, a
model-capability frontier that neither our levers nor the winners' move. The next real gain there
comes from a stronger generator or a fundamentally different grounding approach — and the harness,
now carrying five more measured levers and their nulls, is ready to adjudicate whatever comes next.

That readiness is the whole point. The measurement was always the product — and this step is the
cleanest demonstration of why: a paper full of borrowed techniques dropped onto the apparatus with
almost no new scaffolding, because the recall metric, the guardrail, and the comparator were
already there; and when they ran, the same apparatus that could have flattered them instead told
the truth — mostly nulls, one divergence, one small explained positive. A lever that doesn't move
the number is worth knowing about, and worth saying plainly. That was the discipline the whole
series was built to keep.
