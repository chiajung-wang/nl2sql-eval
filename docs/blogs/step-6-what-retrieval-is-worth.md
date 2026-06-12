---
title: "Step 6 — What Retrieval Is Worth"
subtitle: "Schema-RAG over table metadata, a loop-aware re-trigger, a table-scope guardrail — and a retrieval lift that comes out negative, with the recall metric to explain exactly why"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 6
date: 2026-06-13
author: Chia-Jung Wang
tags: [llm, nl2sql, rag, retrieval, schema, evaluation, measurement, guardrails]
---

# Step 6 — What Retrieval Is Worth

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness and the apparatus around it are the *product*. Step 5 measured what
> self-correction is worth and found, honestly, zero on our slice. Step 6 measures
> what *retrieval* is worth — and the answer is the sharpest result yet: on the
> dbs we can actually test, schema-RAG **lowers** accuracy by 12.5 points. The
> point of the chapter is not that retrieval is bad. It's that we can say exactly
> *why*, with a number — because we built the metric that explains it.

Every RAG demo opens the same way: a giant schema, a clever retriever, a correct
answer, and the implicit promise that retrieval made it possible. Almost none of
them tell you what retrieval *cost*. Retrieval is a filter, and a filter that
removes the wrong thing makes the system worse — silently, because the query still
runs and still returns rows. Step 6 builds schema-RAG and then refuses to take its
value on faith. It measures it.

Step 6 came in five slices. The first four build the machinery; the fifth produces
the number that judges it.

---

## 1. Retrieval over *schema metadata*, not documents

The Step-3 baseline dumps the **entire** schema into the prompt. That's fine for a
3-table db and impossible for a 100-table one — and it's wasteful even when it
fits, because most tables are irrelevant to any one question. So `retrieve.py`
replaces the dump with **schema-RAG**: index each table's columns, types, and *a
few sample values per column* (knowing `status ∈ {failed, settled}` changes the
SQL you write), then score tables against *this* question and hand `generate` only
the relevant ones.

Two deliberate choices. The retriever is **deterministic** — lexical token overlap
between the question and each table's name/columns/samples, not an embedding model
— because a deterministic retriever is testable and its failures are legible. And
it's **import-shared**: the harness and the demo build the index and call retrieve
the same way, so what's measured is what's shipped.

## 2. Make the loop *retrieval-aware*

Step 5 gave the pipeline a correction loop: an execution error feeds back into
regeneration. But retrieval introduced a new failure the regenerator can't fix —
*retrieving the wrong tables*. If the model never sees the table it needs, asking
it to try again with the same too-narrow schema is pointless.

So the loop became **retrieval-aware**: a `column/table-not-found` execution error
routes back into *retrieval*, not just generation. The re-retrieve **widens** the
schema (`max_tables → 2× → 4× …`, reaching the full dump at the widest) with the
missing identifier as a lexical nudge — all inside the same Step-5 capped budget.
This closes the asymmetry where everything looped except the one stage that most
needed to.

## 3. The metric that makes the silent failure visible

Here is the failure that should keep you up at night. The retriever drops a needed
table. The model, not knowing it's missing, writes **valid SQL over the tables it
*was* given**. The query runs clean. It returns rows. The rows are wrong. There is
no error, no exception, no signal — just a confident wrong answer that looks
exactly like a right one.

You **cannot fix this at runtime** (fixing it is just solving Text-to-SQL). But you
can *measure* it, and that measurement is the whole point of the slice:

> **Retrieval recall** = |retrieved tables ∩ gold-query tables| / |gold-query
> tables|.

The gold query's tables are extracted **from the sqlglot AST**, never a string
scan — an alias, a `FROM` inside a string literal, or a CTE name can't fool it.
(That last one is a real bug we caught in review: a CTE reference parses as a
`Table` node, so a naive extractor counts it as a gold table the retriever could
never return, permanently deflating recall. The fix subtracts CTE names; the test
pins it.) Recall is reported **alongside** accuracy on every run, because accuracy
alone is blind to the silent case — and, as we'll see, recall is what turns the
headline number from a mystery into an explanation.

## 4. The guardrail that needed retrieval to exist

Step 4 built the guard gate but deliberately deferred one check: **table-scope** —
"does this query touch a table it shouldn't?" — because "shouldn't" needs a per-db
allowed-tables list, which is exactly the schema metadata Step 6 now has. So the
gate is completed here: a deterministic AST check that rejects a candidate
referencing a table outside the db's real tables.

The interesting part is how it **reconciles with the re-trigger**. An out-of-scope
table reference is, usually, the *too-narrow-retrieval* symptom — the model
reached for something it couldn't see properly. The guardrail spec allows a failed
check to "reject **or** feed back as a correction signal," so we chose feedback: a
table-scope rejection **re-triggers retrieval** (widening) within the budget rather
than hard-stopping. Security rules (read-only, dangerous-op, cost) still end the
run immediately; only table-scope — the one that's really a retrieval problem in
disguise — loops. At budget exhaustion it becomes a terminal `GUARDRAIL_REJECTED`,
having never touched the database. The guardrail and the recovery loop, which look
like they'd fight, turn out to compose.

---

## 5. The number — and the honesty it demands

The first four slices are machinery. The fifth points it at a **frozen,
large-schema slice** — 40 questions from BIRD dbs above the Step-3 5-table cap,
seeded, stratified, checked in, and disjoint from the small-schema slice — and runs
the *same pipeline twice*: once with the naive full dump, once with schema-RAG.
Same questions, same dbs, same dialect, same evidence. The only difference is the
schema source. The result:

| Mode | pass@1 | retrieval recall |
|---|---|---|
| naive full-schema dump | **0.700** (28/40) | — |
| schema-RAG | **0.575** (23/40) | **0.942** |
| **lift** | **−0.125** | |

**Schema-RAG made it worse.** Twelve and a half points worse.

The instinct is to hide this, or to tune the slice until retrieval wins. The
discipline is to explain it — and the metric we built in slice 3 explains it
exactly. Recall is **0.942**: about 5.8% of the gold tables were *missed* by the
retriever. On these BIRD dev dbs (≤14 tables) the whole schema **already fits** the
model's context, so the naive dump hands the model *every* table — a recall of
1.0, by construction. Schema-RAG, whose entire job is to *drop* tables to fit a
budget, occasionally drops a needed one, and each drop is a silent wrong answer.
The losses concentrate exactly where you'd predict: the 10-to-14-table dbs, where
the budget actually bites.

So the finding is precise, not just "RAG underperformed":

> **Retrieval is not free.** Its benefit is *conditional* on the schema not fitting
> the prompt. On schemas that fit, retrieval can only lose information — and the
> recall metric measures precisely how much it lost. The lift turns positive where
> the dump overflows; these dbs don't, so it doesn't.

This is the twin of Step 5's `+0.000`. There, the eval proved self-correction added
no accuracy rather than letting a headline pass@k imply otherwise. Here, it proves
retrieval *subtracted* accuracy, and hands you the recall number that says why.
That is the entire thesis of the project in one table: **a measurement apparatus
that tells you the truth about your LLM system, including when the truth is
inconvenient.**

An honest reviewer pushed on exactly this — *is the negative number real, or an
artifact of a too-aggressive retriever?* The answer held up: both modes run the
same cases through the same import-shared pipeline; the only delta is full-dump vs
index; recall 0.942 is arithmetically consistent with five questions flipping to
wrong; and the slice's own metadata was corrected to stop calling dbs that fit the
context "overflowing." The number is the number.

---

## What we refused to build

- **A cherry-picked slice.** We could have hunted for questions where retrieval
  wins and reported +0.x. The slice is frozen, seeded, and stratified *before* the
  number is known — so the number is a measurement, not a selection.
- **A fix for the silent case.** Recall measures the wrong-schema failure; it does
  not pretend to repair it at runtime. Trying to would be trying to solve
  Text-to-SQL, which is not what this project claims to do.
- **An embedding retriever, yet.** A deterministic lexical retriever is testable
  and its misses are legible. A heavier retriever is a later optimization to
  *measure against this baseline* — not a way to make slice 5's number prettier.

---

## What's next

- **Step 7** — swap the hand-rolled state machine for **LangGraph** (proving
  behavioral parity through the harness), then **LiteLLM** for provider
  abstraction, and a **cross-provider** comparison — the same frozen slices,
  different models, every number traceable.
- **Step 8** — wire the observability seams to Langfuse so any failing question is
  diagnosable from its trace, with redaction enforced.

Step 5 measured what a retry is worth. Step 6 measured what a retrieval is worth,
and the honest answer on our data is *less than nothing* — a result that's only
embarrassing if you don't have the recall metric to explain it, and a genuine
finding if you do. The apparatus did its job: it stopped a plausible story
("retrieval helps") from becoming an unverified claim. That was always the product.
