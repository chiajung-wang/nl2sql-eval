---
title: "Step 6, Follow-up — When Retrieval Actually Pays"
subtitle: "Step 6 said schema-RAG only earns its keep where the schema overflows the prompt. So we went looking for that regime — and found that on a public benchmark, with today's context windows, it barely exists. Two experiments, one adaptive gate, a cost axis, and four overclaims the apparatus caught on its own author."
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 6.5
date: 2026-06-15
author: Chia-Jung Wang
tags: [llm, nl2sql, rag, retrieval, schema, evaluation, measurement, sampling-noise, context-window]
---

# Step 6, Follow-up — When Retrieval Actually Pays

> **Where we left off.** Step 6 measured what schema-RAG is worth and got a
> negative number: **−0.125** pass@1. The explanation was precise — on BIRD dbs
> that *fit* the model's context, retrieval can only *drop* a needed table and
> lose — and it ended on a promise: retrieval's lift "turns positive where the
> dump overflows." This follow-up cashes that promise. It turns out the honest
> answer is more interesting than a positive number: with a 200K-token context
> window, the regime where schema-RAG pays has *narrowed to almost nothing* on a
> public benchmark — and proving that, then building a gate that acts on it, was
> the work.

Step 6 closed with a hypothesis: schema-RAG loses on schemas that fit and wins on
schemas that overflow. The natural next move is to find the overflow regime and
show the win. So the first thing I did was the unglamorous thing — I measured
whether BIRD even *has* an overflow regime.

It doesn't.

The largest schema in the frozen Step-6 slice, `european_football_2`, renders to
**~3,820 tokens** (with sample values). The biggest BIRD dev db by table count,
`formula_1`, is 13 tables / ~1,979 tokens. A modern context window is 200,000
tokens. **Nothing in BIRD comes close to overflowing it.** Schema-RAG was born in
2023, when context windows were 4–8K tokens and you *had* to retrieve to fit. That
pressure is gone for anything a public NL-to-SQL benchmark contains. That is the
first finding, and it reframes everything that follows: we are not going to
demonstrate a natural overflow, because there isn't one. We are going to be honest
about that, and measure the mechanism under a *deliberately imposed* budget
instead.

Two issues. The first finds where retrieval pays under a budget; the second builds
the system that acts on it.

---

## 1. A budget is a policy, not a context limit (#75)

If the schema always fits the window, why would you ever not send all of it? Cost
and latency. Every token of schema rides in *every* call; a real system caps it.
So we stop pretending the budget is the model's hard limit and treat it as what it
actually is in production — **a configured cost/latency policy** — and ask the
sharp question under that policy:

> Given a fixed schema-token budget, is it better to **truncate** the schema
> (declaration order, what a non-retrieving system is forced to do) or to
> **retrieve** the relevant tables into the same budget?

We swept the budget from 256 to 4096 tokens over the frozen Step-6 slice, running
the same import-shared pipeline both ways. The first draft of the result said
"RAG-select beats truncation at every budget." That sentence did not survive
review.

| budget | naive-truncate | RAG-select | gap | RAG recall | selection divergence |
|---|---|---|---|---|---|
| 256 | 0.475 | 0.500 | +0.025 | 0.450 | 0.750 |
| 512 | 0.525 | 0.625 | +0.100 | 0.569 | 0.750 |
| 1024 | 0.525 | 0.600 | +0.075 | 0.752 | 0.650 |
| 2048 | 0.575 | 0.650 | +0.075 | 0.900 | 0.350 |
| 4096 | 0.625 | 0.675 | +0.050 | 1.000 | 0.000 |

Read the bottom row carefully, because it is the whole lesson. At 4096 tokens the
**selection divergence is 0** — every schema fits, so truncation and retrieval pick
the *identical* tables and send the generator *identical prompts*. And yet RAG-select
still "wins" by +0.050. That is impossible if the comparison were clean. The only
explanation is **sampling noise**: generation runs at non-zero temperature, so two
independent runs on the same prompt differ by ~2 questions out of 40. **+0.050 is
the noise floor.**

Once you know the noise floor is ~0.05, the rest of the column deflates honestly.
The peak gap is +0.100 at 512t — about twice the floor, the one point that's
plausibly real. The rest sit within a single noise-width of zero. So the headline
isn't "retrieval beats truncation by up to ten points." It's:

> Under a tight budget, retrieval keeps the **right** tables and truncation cuts
> blindly — and the proof of that is **recall**, which climbs monotonically
> 0.450 → 1.000 with the budget. The pass@1 advantage is real but small against
> sampling noise on 40 questions. The robust signal is recall, not accuracy.

To make the convergence point principled rather than a gap that happens to cross
zero through noise, the harness reports **selection divergence** — the fraction of
questions where the two modes actually pick different tables — and defines
convergence as divergence hitting 0, not the accuracy gap closing. Noise can move
an accuracy gap; it cannot make two identical prompts diverge.

## 2. The gate the −0.125 was asking for (#76)

Step 6's −0.125 was never really a verdict on retrieval. It was a **mechanism
bug**: `retrieve` caps at `max_tables` (8) and so drops tables *even when the whole
schema would have fit the prompt*. On a 13-table db that fits the budget easily,
the Step-6 RAG path still threw away 5 tables and hoped. Of course it lost.

The fix writes itself once #75 has named the regimes: **don't retrieve when you
don't have to.** The adaptive gate is a deterministic, pre-generation decision:

```
if the full schema fits the configured token budget:   dump it all   (mode = "full")
else:                                                   retrieve      (mode = "rag")
```

No LLM in the decision, one config key (`DEFAULT_SCHEMA_TOKEN_BUDGET = 2048`), and
it lives in the one import-shared `retrieve` stage, so the demo and the harness get
the same gate. On the frozen slice at 2048t it routes **24 of 40** questions to a
full dump and **16** to RAG. Three modes, same slice:

| mode | pass@1 |
|---|---|
| naive full dump (the ceiling, ignores budget) | 0.675 (27/40) |
| always-RAG (capped — the Step-6 loser) | 0.625 (25/40) |
| **adaptive @2048t** | **0.675 (27/40)** |

Adaptive ties the full-dump ceiling and edges always-RAG by +0.050. And by now you
know the discipline: **that is within the noise floor.** Worse for the tidy
story — the dramatic −0.125 from Step 6 **did not reproduce this run at all**;
always-RAG trailed naive by only 0.050 here. The original gap, like these, carried
sampling variance.

So I am not going to tell you the gate bought five points. It didn't, measurably.
What it bought is **structural**:

> The gate makes the deterministic cost/accuracy-optimal choice *per database* — it
> never pays the table-cap's drop risk on a schema that fits, and it respects the
> budget on a schema that doesn't. Measured on this slice it never does worse than
> either baseline. It is a **no-regret** routing, not an accuracy lift.

## 3. The cost axis — and the bug it found

A reviewer made the sharp objection: the whole thesis is *"with big windows, RAG's
job becomes cost control"* — so where are the cost numbers? Fair. The gate's lever
is **which tables ride in the prompt**, so the honest cost metric is the rendered-
schema token footprint, representation held constant across modes:

| mode | pass@1 | schema tokens (mean) | (max) |
|---|---|---|---|
| naive full dump | 0.675 | 2,173 | 3,820 |
| always-RAG (capped) | 0.625 | 1,470 | 3,820 |
| **adaptive @2048t** | 0.675 | **1,403** | **2,038** |

There's the cost-control win, quantified: adaptive matches the full-dump accuracy
at **35% fewer schema tokens**, and — the point of the gate — its **per-call max is
bounded by the budget** (2,038 ≤ 2,048), where naive's runs to 3,820.

But writing that table is what caught the bug. The *first* version of the gate
bounded the full-vs-RAG **decision** by the budget, then ran its RAG branch with
the old `max_tables=8` cap. On a db with few-but-large tables (`european_football_2`:
7 tables, 3,820 tokens) the gate correctly said "too big, retrieve" — and then RAG
returned all 7 tables anyway, because 7 ≤ 8. The gate's max was still **3,820**: it
did not enforce the ceiling it advertised. You could not see this in the accuracy
numbers; you could only see it by **measuring the tokens**. The fix is one line —
the RAG branch fits the *budget*, not a table count — and the max drops to 2,038.

That is a real, defensible improvement to the architecture — the *reason* it exists
is a number we measured in #75, and the *bound it actually enforces* is a number we
only got right by measuring cost. The measurement shaped the system, twice.

---

## The apparatus caught me four times

This follow-up is, more than anything, a story about an eval harness doing its job
on its own author. Across the work it caught four overclaims:

1. **"The largest schemas exceed 4096t, so truncation keeps dropping tables."**
   False — the largest is 3,820t; at 4096t nothing truncates. The review forced
   the divergence metric that proved it.
2. **"RAG beats truncation at every budget."** Technically true, but most of the
   gap is sampling noise; the honest signal is recall.
3. **"The adaptive gate recovers the −0.125 loss."** The −0.125 didn't even
   reproduce, and the gate's edge is within noise. The honest claim is structural.
4. **"The gate bounds per-call cost at the budget."** False until the cost table
   was written: its RAG branch was table-capped, not budget-bounded, so it still
   blew the ceiling on a few-but-large-table db. Measuring cost found it; one line
   fixed it.

Each correction made the result *less* of a headline and *more* of a finding. A
portfolio that only ever reports clean wins is indistinguishable from one that
doesn't measure carefully. This one keeps catching its own author mid-overclaim —
in writing, with the commit that fixed it — which is the strongest evidence that
the measurement is real.

## What we refused to build

- **A larger dataset to manufacture an overflow.** BIRD doesn't overflow modern
  context, and neither does BIRD-train at any table count it actually contains.
  Demonstrating literal overflow would mean importing an enterprise-scale schema —
  a different project (and the natural home of the Step-10 BigQuery reach), not a
  way to make this number prettier.
- **A significance claim we can't support.** Forty questions and temperature-1.0
  generation give a ~0.05 noise floor. Rather than report sub-floor gaps as wins,
  we report the floor and let the recall trend carry the claim.
- **A gate that's clever instead of correct.** The decision is a token-threshold
  comparison, deterministic and testable, defaulting to off (`budget_tokens=None`
  is the prior behavior). No learned router, no LLM in the loop.

## What's next

- **Step 7** — swap the hand-rolled state machine for **LangGraph** and provider
  access for **LiteLLM**, then a **cross-provider** table on the same frozen
  slices. A bigger model with a bigger window only sharpens this follow-up's
  thesis: the more context you have, the less schema-RAG is buying you, and the
  more its job becomes *cost control* — exactly what the adaptive gate is for.
- **Step 8** — wire the observability seams to Langfuse; the `retrieval_mode` the
  gate records on every span becomes a trace you can actually read.

Step 6 asked what retrieval is worth and answered "less than nothing, here's why."
This follow-up asked where it *would* be worth something, and the honest answer is:
on a public benchmark, with a modern context window, **almost nowhere** — its value
has quietly migrated from *fitting the schema* to *controlling the bill*. So we
built the gate that does the second job, proved it never regresses, and resisted
every temptation to dress a noise-floor gap up as a win. The apparatus told the
truth about retrieval one more time. That was always the product.
