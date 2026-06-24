---
title: "The Wrapper Is the Product"
subtitle: "A case study in rigorously evaluating and operating an LLM system — what it takes to prove a Guardrailed Agentic NL-to-SQL agent works, catch it when it breaks, and run it day to day, with every number traceable to a config and a commit"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 0
date: 2026-06-24
author: Chia-Jung Wang
tags: [llm, nl2sql, evaluation, guardrails, observability, llmops, prompt-ci, measurement]
---

# The Wrapper Is the Product

Anyone can wire an LLM to a database. You give a model a schema and a question, it
writes SQL, you run it, you show the rows. A weekend project. The hard part — the
part that separates a demo from a system you'd operate — is everything around that
call: **proving it works, catching it when it breaks, and running it day to day.**

So this project inverts the usual emphasis. The natural-language-to-SQL agent is
the *workload*; the **eval harness, observability, and prompt-CI/CD wrapper around
it is the product.** The agent exists to give the apparatus something to measure.
Every claim below links to its committed entry in [`RESULTS.md`](../../RESULTS.md)
and names the commit that produced it — because a number you can't trace to a
config and a commit is an opinion, not a result.

What follows is the whole arc, with the receipts. Each section links to the
step-by-step post that built it.

---

## 1. The inversion: build the measurement before the feature

The temptation in an LLM project is to build features and *then* figure out how to
evaluate them. That order is backwards, because without a trustworthy scorer you
can't tell whether a feature helped, hurt, or did nothing — and "did nothing"
dressed up as a headline is the most common way LLM demos mislead.

So the eval came first and stayed a peer of the source, never subordinate. The
pipeline is an **instrumented state machine** — `retrieve → generate → guard →
execute → correct → redact` — wrapped by a harness that treats it as `question →
result`. The same compiled graph is **import-shared** by the harness and the demo,
so there is never drift between what is measured and what is shown. And it has
**two exits**, which turns out to be the load-bearing design decision of the whole
system:

- the **raw verified result**, scored against gold *upstream of redaction*;
- the **presented result**, post-redaction — the only thing ever shown or logged.

Hold onto that split. It's what lets the harness score the truth while guaranteeing
raw PII never reaches a log, a trace, or a screen.

---

## 2. How I know my evaluator is correct

Before a scorer can certify the system, something has to certify the scorer — or
every downstream number inherits its bugs. The first hard rule: **execution
accuracy is canonicalized result-set comparison, never SQL string-match.** Two
different queries can be equally correct; comparing their text would fail correct
answers and is the single most common way NL-to-SQL evals quietly lie.

The comparator is proven against a **golden fixture** of `(gold, candidate,
expected_verdict)` triples — column reordering, row reordering, type coercion,
near-duplicate floats, the cases that trip naive comparison. The comparator must
pass its *entire* fixture, and the committed rule set is audited per-rule against
the official BIRD evaluator. ([Step 2 — Proving the Scorer](step-2-proving-the-scorer.md).)

Only once the scorer was trustworthy did it get pointed at a real benchmark.

---

## 3. The first real number

On a **frozen, seeded, stratified** 50-question BIRD slice, the naive
schema-dump baseline scores **pass@1 0.420 (21/50)**
([RESULTS.md](../../RESULTS.md#log), `5d9d8ae`). Frozen and seeded so the number
is reproducible; stratified by difficulty so it isn't accidentally all-easy. It's
not a leaderboard-topping number, and that's fine — it's an *honest anchor* every
later change is measured against. ([Step 3 — The First Real Number](step-3-the-first-real-number.md).)

---

## 4. Deterministic guardrails, measured against a red team

Guardrails are not a feature you claim; they're a feature you *measure*. They are
**deterministic sqlglot AST checks**, pre-execution — never regex for SQL
semantics, never an LLM judge. Read-only enforcement (block writes/DDL),
dangerous-op blocking (stacked statements, `ATTACH`/`DETACH`, `PRAGMA`),
cost/complexity heuristics, and per-db table-scope checks.

Their catch rate is reported against a **red-team fixture** of injected dangerous
queries: **29/29 caught (100%)**, with **43/43 verdicts correct** — every benign
control allowed, every attack blocked ([RESULTS.md](../../RESULTS.md#log),
`e56fbcd`). The set spans write/DDL (including `REPLACE`-as-`Command` and
CTE-wrapped writes), dangerous ops, cost explosions, and prompt-injection payloads.
([Step 4 — Proving the Guardrails](step-4-proving-the-guardrails.md).)

This is the methodology that recurs everywhere: *prove a safety mechanism by
feeding it exactly what it must catch.*

---

## 5. What self-correction is worth — and the honesty to report zero

Here's where building the measurement first pays off. Self-correction — feeding an
execution error back into regeneration within a capped retry budget — *sounds* like
an obvious win. The twin metric measures it: **pass@1** (correction off) vs
**pass@k** (correction on), on the same slice, with the added cost the gap buys.

The result: **pass@1 0.420 → pass@3 0.420, gap +0.000**
([RESULTS.md](../../RESULTS.md#log), `7ae5bb5`). The loop **never fired** — of the
29 failures, zero were execution errors (the only kind the loop can feed back); the
rest were *wrong answers* (clean execution, wrong result) and a couple of guardrail
rejections. On this slice the failures are **semantic, not syntactic** — you can't
retry your way out of misunderstanding the question.

A headline-chasing writeup would have reported pass@3 and implied self-correction
helped. The twin metric proves it added *exactly nothing here* — and proving the
zero is the feature. ([Step 5 — What Self-Correction Is Worth](step-5-what-self-correction-is-worth.md).)

---

## 6. What retrieval is worth — and the silent failure only recall can see

Schema-RAG — retrieving the relevant tables instead of dumping the whole schema —
is supposed to help on large schemas. Measured on a frozen large-schema slice, it
*hurt*: **pass@1 0.700 → 0.575, a lift of −0.125**, with retrieval recall **0.942**
([RESULTS.md](../../RESULTS.md#log), `ff342d7`).

Why? On these BIRD dbs the whole schema still *fits* the model's context, so the
naive dump already hands the model every table — while RAG, whose job is to *drop*
tables to fit a budget, occasionally drops a **needed** one. Recall 0.942 means
~5.8% of gold tables were missed, and those become wrong answers. This is the
**silent wrong-schema failure**: valid SQL over the wrong tables, no error,
invisible to accuracy alone. Recall is the metric that *sees* it — you can't fix it
at runtime, only measure it.

A controlled follow-up made the trade-off legible: under a configured schema-token
budget, where the schema *overflows*, retrieval's recall climbs **0.450 → 1.000**
and its pass@1 advantage peaks at **+0.100 @512 tokens**
([RESULTS.md](../../RESULTS.md#log), `1c2f5eb`). Retrieval is not free; it pays
exactly where the schema doesn't fit, and the recall gap is the honest signal.
([Step 6 — What Retrieval Is Worth](step-6-what-retrieval-is-worth.md) ·
[Follow-up — When Retrieval Actually Pays](step-6-follow-up-when-retrieval-pays.md).)

---

## 7. Operating it: a framework swap proven to change nothing

Only after the logic was proven did the framework arrive — **LangGraph** for the
state machine, **LiteLLM** for the provider boundary. The point was the *order*:
you introduce a framework after the logic is pinned down, then use the harness to
prove the swap was behavior-preserving.

The most reassuring number in the project: re-running the exact Step-3 baseline
through the new LangGraph + LiteLLM stack gives **pass@1 0.420 → 0.420** — identical
([RESULTS.md](../../RESULTS.md#log), `2040ef9`). The harness was built to be able to
say "this refactor is a no-op," and it did.

With one provider boundary reaching many backends, model choice became a table —
accuracy × cost × latency over the frozen slice, one row per model. Best pass@1
**0.540** (`gemini-3-flash`), while the cheapest model ran **~70× less** per run
than the priciest ([RESULTS.md](../../RESULTS.md#log), `26328de`). A table you can
reproduce beats an opinion you can't.
([Step 7 — The Framework Where It Earned Its Place](step-7-the-framework-where-it-earned-its-place.md).)

---

## 8. Operating it: diagnosable from a trace, without ever logging PII

A system you can't see inside is a system you can't operate. Every run emits a
**Langfuse** span per stage (one run = one trace), capturing cost, latency, and
tokens natively. And this is where the two-exit design earns its keep: the harness
scores the *raw* result upstream of redaction, while the only thing that reaches a
span or a log line is the *presented* result, whose PII columns are masked —
column-aware, deterministic, schema-driven.

It's enforced, not assumed: an end-to-end test runs a real PII value through the
full pipeline and asserts it reaches **neither a span nor a log line** while the raw
exit still holds it for scoring. A failing question is debuggable from its trace —
the retrieved tables, the generated SQL per attempt, the guard verdict, the
execution error, the terminal state — with no raw PII anywhere
([RESULTS.md](../../RESULTS.md#log), `a376fec`).
([Step 8 — Diagnosable From Its Trace, Without Ever Logging PII](step-8-diagnosable-without-leaking-pii.md).)

---

## 9. Operating it: a prompt change that tells you if you regressed

The cheapest, riskiest edit in an LLM system is a prompt change — highest-leverage,
easiest to make, least tested. So prompts are externalized as version-controlled
templates, and a **GitHub Action runs the harness on a frozen slice whenever a
prompt changes**, posting the pass@1/pass@k deltas to the pull request.

The demonstration: a reasonable-looking edit — "let the model explain its
reasoning" — relaxes the load-bearing *return ONLY the SQL* rule, the prose breaks
SQL extraction, and pass@1 collapses **0.417 → 0.000, Δ −0.417**
([RESULTS.md](../../RESULTS.md#log), `157fe6b`). The CI caught it before merge. (It
even surfaced a latent guard crash on the way — an untokenizable candidate that had
been crashing the run instead of bucketing into a terminal state, now fixed.)
([Step 9 — A Prompt Change That Tells You If You Regressed](step-9-a-prompt-change-that-tells-you-if-you-regressed.md).)

---

## 10. Honest limits

The point of all this rigor is to be able to state limits precisely rather than
hand-wave them:

- **Single-db per run.** The db identity is an input (BIRD tags each question);
  cross-database routing is explicitly out of scope. This is a one-db NL-to-SQL
  system measured well, not a router.
- **Silent retrieval failures are measured, not fixed.** Recall surfaces the
  wrong-schema failure, but the system doesn't repair it at runtime — closing the
  loop on retrieval misses is future work, and saying so is more useful than
  pretending recall 0.942 is recall 1.000.
- **The slices are small, and sampling noise is real.** At non-zero temperature on
  40–50 question slices, two runs of the *same* prompt differ by ~0.05; several
  reported gaps are deliberately read against that floor rather than over-claimed.
- **BIRD schemas fit modern context windows**, so the retrieval results are a
  *controlled experiment* under a configured budget, not a natural-overflow claim —
  stated as such.
- **BigQuery is a documented, deliberately-deferred reach.** The cloud-warehouse
  executor carries real integration risk (auth, dialect, cost); it was quarantined
  so it could never block the parts that make the project legible.

None of these are confessions dragged out under review. They're the *output* of
building the measurement first: when you can see the truth, you can state its edges.

---

## What the apparatus is

Strip away the steps and the thesis is one idea applied ten times: **build the
thing that can tell you the truth before you build the thing you hope is true.** A
proven comparator before a benchmark number. A red-team fixture before a guardrail
claim. A twin metric that can report self-correction is worth *zero*. A recall
metric that sees the failure accuracy can't. A harness that proves a framework swap
changed nothing. A trace that's debuggable without leaking PII. A CI job that
catches a prompt regression before it ships.

The NL-to-SQL agent is just the workload. The measurement apparatus — the part that
turns "it seems to work" into a number with a commit attached — is the product. If
you want to operate an LLM system rather than demo one, that's the part worth
building first.

*Every number in this post links to its committed run in
[`RESULTS.md`](../../RESULTS.md). The full build is narrated step by step in the
[series index](.); the code is import-shared between the eval harness and the demo,
so what's measured is exactly what's shown.*
