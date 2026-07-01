---
title: "Step 12 — Borrowing the Winner's Playbook"
subtitle: "Step 11 named the frontier — table selection on multi-table joins — and left the method open. The #1 BIRD submission supplies five specific ones. This step imports all five as deterministic machinery, and the striking part is that every one of them plugs into a piece of apparatus we had already built: the retrieval-recall metric, the guardrail shape, the comparator. The accuracy A/Bs are deferred on a key; the machinery and its offline proofs are the deliverable."
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 12
date: 2026-07-01
author: Chia-Jung Wang
tags: [llm, nl2sql, evaluation, optimization, schema-linking, data-profiling, majority-voting, measurement, deferred-verification]
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

One honesty note up front, because it shapes everything below. This project's discipline
is that **no number ships without a live run behind it**, and the live runs here need an
API key and spend the project hasn't authorized yet. So Step 12 deliberately ships the
**machinery and its offline, deterministic proofs** — and *defers* the accuracy A/Bs, each
one recorded in `RESULTS.md` as pending, gated on a key. That is not a dodge: for four of
these five levers the deterministic core *is* the hard part and *is* fully provable offline,
and — per the lesson Steps 5 and 11 kept teaching — several of them may well be honest nulls
on a strong generator anyway. The finding of this step is the machinery, built correctly and
proven to do what it claims, ready for the A/B the moment a key exists.

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
now a hard error. The live linking run is deferred; the mechanism is proven.

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
the deferred headline; the machinery that would run it is complete and proven.

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
on on-column and unknown literals, and regenerates through the graph. The live trigger /
recovery / **false-steer** rates are the deferred metric — value with its price, the Step-5
twin pattern again.

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
(unanimous / majority / no-majority) is the diagnostic that would explain the gap; the value, if
any, lives on the weaker generators — exactly where the self-correction twin found its lift. The
live strong-vs-weak twin is deferred; the selector is done.

---

## The scoreboard: machinery shipped, numbers pending — on purpose

| # | Lever | Reuses | Offline proof | Live A/B |
|---|---|---|---|---|
| 138 | task-alignment schema linking | Step-6 recall metric | 17 tests; harvest/union/degrade | deferred |
| 139 | bad-construction soundness checks | Step-4 guardrail shape | catch 1.000 / FP 0.000 (fixture) | deferred |
| 140 | profiling-derived metadata | SQLAlchemy executor; PII boundary | 26 tests; recovers paper's examples | deferred |
| 141 | literal→field steering | value index; `correct.py` loop | 20 tests; recovers County→District | deferred |
| 142 | result-set majority voting | **Step-2 comparator** | 22 tests; comparator-rule reuse | deferred |

Every "deferred" is a real `RESULTS.md` row that names what's pending and why (no key), not a
blank. Reproduce any offline proof directly:

```bash
uv run pytest tests/test_schema_linking.py tests/test_soundness.py \
              tests/test_profiling.py tests/test_literal_field.py tests/test_voting.py
```

---

## What we refused to do

- **Fabricate the accuracy numbers.** The whole series' credibility is that a number names a
  live run, a slice, and a commit. With no authorized key, the honest move is to ship the
  machinery and mark every A/B pending — not to invent a lift the apparatus didn't measure.
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

Step 11 found the wall; Step 12 imported the demolition tools and proved they're built
correctly, deterministically, and to the project's boundaries — then, true to the discipline,
declined to report a lift it couldn't measure. The one thing standing between this machinery and
a verdict is an authorized live run: point the profiler at the real BIRD databases, generate the
cached summaries once, and run the five A/Bs — supplied vs profiling vs fused, linking vs RAG,
attempt-1 vs majority vote, ± the soundness and steering checks — on both a strong and a weak
generator, the strong/weak contrast where every lever in this series showed its true shape. The
apparatus is ready to adjudicate all five the moment the key exists.

That readiness is the whole point. The measurement was always the product — and this step is the
cleanest demonstration of why: a paper full of borrowed techniques dropped onto it with almost no
new scaffolding, because the recall metric, the guardrail, and the comparator were already there,
waiting to be pointed at a new question.
