---
title: "Step 7 — The Framework Where It Earned Its Place"
subtitle: "Introducing LangGraph and LiteLLM only after the logic was proven — then using the harness to prove the refactor changed nothing, and turning model choice into a measured accuracy × cost × latency table"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 7
date: 2026-06-17
author: Chia-Jung Wang
tags: [llm, nl2sql, langgraph, litellm, openrouter, evaluation, cost, latency, measurement]
---

# Step 7 — The Framework Where It Earned Its Place

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness and the apparatus around it are the *product*. Steps 1–6 built and measured
> the pipeline on a deliberately plain, hand-rolled state machine. Step 7 finally
> introduces the framework (**LangGraph**) and the multi-provider gateway (**LiteLLM**)
> — and the whole point is the *order*. You introduce a framework after the logic is
> proven, not before, and then you use the harness you already built to prove the swap
> was **behavior-preserving**. The headline number is the most reassuring kind:
> **pass@1 0.420 → 0.420**, byte-for-byte unchanged across the refactor.

There is a strong temptation, at the start of an LLM project, to reach for the
framework first — LangGraph for the agent, a provider gateway for the models — and
build the logic inside it. I deliberately didn't. For six steps the pipeline was a
hand-rolled `while` loop and a single direct provider call, because **framework and
provider churn must never be able to mask a logic bug** while the logic is still being
proven. When a number moves, you want exactly one suspect.

By Step 7 the logic *is* proven: a comparator with a golden fixture (Step 2), a real
BIRD number (Step 3), a measured guardrail (Step 4), a rigorously-zero pass@k gap
(Step 5), and a retrieval lift quantified down to its sampling noise (Step 6). Now the
framework earns its place — and the harness is standing by to keep it honest.

---

## #50 — LangGraph, as a behavior-preserving refactor

The pipeline was always *a graph*: a generate→guard→execute spine, a capped correction
loop that re-enters `generate` on an execution error, a retrieval re-trigger that
widens the schema on a not-found, and terminal-state branching. Re-expressing that as
LangGraph nodes and conditional edges is a genuine fit, not framework-for-its-own-sake.
The conditional edges encode *exactly* the branches the `while` loop had:

```python
# pipeline/graph.py — the loop, now as a compiled StateGraph
g.add_edge("generate", "guard")
g.add_conditional_edges("guard", _route_after_guard,
                        {"execute": "execute",
                         "scope_re_retrieve": "scope_re_retrieve", END: END})
g.add_conditional_edges("execute", _route_after_execute,
                        {"correct": "correct", END: END})
g.add_edge("correct", "generate")          # the correction loop, as an edge
```

Two rules made this safe rather than scary. First, **`run_pipeline` kept its exact
signature and `RunState` return** — so `eval/harness.py`, the demo, and every test call
the identical entry point; nothing downstream knows the internals changed. Second, the
terminal-state classifier stayed in the harness, never migrating into `graph.py` or
`state.py`. The mutable run is one channel; the loop-local bookkeeping rides alongside;
the static per-run inputs travel in `config["configurable"]` so the graph compiles once
at import.

The proof it changed nothing is the entire reason Steps 1–6 came first: the offline
suite — which drives `run_pipeline` with an injected fake client — passes unchanged,
and (below) the live BIRD accuracy is *identical* post-refactor. The harness was built
to be able to say "this refactor is a no-op," and here it does.

One small, honest piece of engineering the live tests later vindicated: each retry
costs a few LangGraph "supersteps," so a high pass@k budget needs the graph's recursion
ceiling scaled to the budget (`recursion_limit = budget * 6 + 25`). A regression test
asserts a budget that *would* trip LangGraph's default ceiling of 25 runs to completion
— so the cap can't silently strangle a legitimate long run.

---

## #51 — LiteLLM, where a provider becomes a string

Step 1's `generate` stage made a direct Anthropic SDK call. Step 7 replaces it with a
one-method boundary — `LLMClient.complete(prompt, *, model, max_tokens) -> LLMResponse`
— backed by **LiteLLM**. The pipeline now depends on that tiny seam and never on a
vendor SDK. The payoff is that **the backend is selected purely by the model
identifier**, with zero provider branching in our code:

```
anthropic/claude-sonnet-4-6           → LiteLLM → Anthropic (direct key)
openrouter/anthropic/claude-sonnet-4  → LiteLLM → OpenRouter → Anthropic
openrouter/openai/gpt-4o-mini         → LiteLLM → OpenRouter → OpenAI
openrouter/google/gemini-3-flash      → LiteLLM → OpenRouter → Google
```

This is the design decision worth dwelling on, because it's a question I had to settle
explicitly: **OpenRouter is a provider *behind* LiteLLM, not a replacement for it.**
LiteLLM stays the boundary (it mirrors the actual gateway stack I was targeting); an
OpenRouter model id is just one more backend the same seam can reach. One key, many
providers — which is what makes the next step cheap.

The boundary also normalizes what comes back: LiteLLM's OpenAI-shaped response and its
`prompt_tokens`/`completion_tokens` are mapped to a provider-agnostic `LLMResponse` with
`input_tokens`/`output_tokens`, so the harness prices any backend identically. And
because nothing imports the Anthropic SDK anymore, that dependency was removed outright
— a swap is only honest if the thing it replaced actually leaves.

---

## #52 — Turning model choice into a table

With one boundary and one key reaching many providers, the cross-provider comparison
becomes a loop: run the import-shared pipeline over the frozen slice once per model and
report **accuracy × cost × latency** per row. That's the "model selection /
cost-latency-quality trade-off" turned from a talking point into an artifact.

Two honesty rails, both demanded by the plan:

- **Cost basis is recorded per row.** An OpenRouter row is priced by *OpenRouter's own
  reported cost* (surfaced by LiteLLM on the response), not a direct-list table — the
  two are not comparable dollar-for-dollar, so the table says which basis each row used.
  This needed a thin extension of the boundary (`LLMResponse.cost_usd`), because a
  Claude-only price table cannot price an OpenAI or Google row at all.
- **OpenRouter routing is pinned** (`allow_fallbacks: false`) so a frozen-slice row
  can't silently switch backend mid-run and quietly break repeatability — a Step-9-style
  invariant the whole project leans on.

The live run, over the frozen 50-question BIRD slice (`generate/v3`, naive schema dump),
three models via OpenRouter, **0 provider errors**:

| model | pass@1 | pass@3 | cost (USD) | mean latency |
|---|---|---|---|---|
| `google/gemini-3-flash-preview` | **0.540 (27/50)** | 0.540 (27/50) | $0.0281 | **1,599 ms** |
| `moonshotai/kimi-k2.7-code` | 0.360 (18/50) | 0.400 (20/50) | $0.1558 | 12,435 ms |
| `deepseek/deepseek-v4-flash` | 0.340 (17/50) | 0.340 (17/50) | **$0.0023** | 4,858 ms |

The trade-off, made concrete: **gemini is both the most accurate *and* the fastest** at
a middling price; **deepseek is ~70× cheaper** ($0.0023 vs $0.1558) but trails on
accuracy; kimi is the priciest and slowest. None of these is a verdict on the models in
general — it's a verdict on *this slice, this prompt, this budget*, which is exactly the
point. A table you can reproduce beats an opinion you can't.

---

## The number that matters most: parity

The cross-provider table proves "best third-party model." It does **not**, on its own,
prove the thing Step 7 actually risked: that introducing LangGraph and LiteLLM didn't
change the pipeline's behavior. That proof is a separate, deliberate measurement —
re-running the *exact Step-3 baseline config* (`anthropic/claude-sonnet-4-6`, naive
dump, `generate/v3`) over the same frozen slice, now executed through the LangGraph
state machine and the LiteLLM boundary:

| Date | Step | Metric | Number | Model | Commit |
|---|---|---|---|---|---|
| 2026-06-17 | 7 | post-refactor parity | **0.420 (21/50)** — unchanged vs baseline | `anthropic/claude-sonnet-4-6` | `2040ef9` |

**0.420 (21/50)** — *identical* to the Step-3 (`5d9d8ae`) and Step-5 (`7ae5bb5`)
baselines, gap +0.000, no correction fired. Same model, same slice, same exact
accuracy. This is what the harness was for all along: to be able to make a framework
and provider swap and then *show*, not assert, that the numbers didn't move.

(This parity entry was missing from my first pass at the results — a two-axis review
flagged it: I'd recorded "best model" but not "refactor changed nothing." The review
catching the gap is the apparatus working on its own author, again.)

---

## What running it live actually taught me

Two bugs only a real run could surface — and the apparatus turning each into a fix:

- **A provider rate-limit aborted the whole job.** The first live run hit OpenRouter's
  shared-pool 429 on a popular model ~22 cases in, and the uncaught error tore down the
  entire multi-model run, writing nothing. The fix: the runner now catches provider
  errors *per case*, buckets them, and surfaces a `provider errors` column — so one
  model's bad spell can't discard the others' completed work, and a depressed accuracy
  is read as infra failure, not model quality.
- **A results row landed in the wrong table.** `append_results` inserted after the last
  `|` line in `RESULTS.md` — which, now that later steps embed their own markdown tables
  in prose, was an *embedded* table, not the Log. The new row wedged itself into the
  Step-6 cost table. The fix anchors the insert on the last *dated* row, with a
  regression test.

And a detour worth naming, because it's the real texture of "model selection": picking
the three models took several iterations. Popular models (`claude-sonnet-4.6`,
`glm-5.2`) were rate-limited on OpenRouter's shared pool. Several candidates
(`deepseek-v4-pro`, `glm-*`) were **reasoning models** that spend output tokens on
hidden chain-of-thought before emitting SQL — at our 1024-token cap they returned *empty*
queries, which would have scored as wrong for a reason that has nothing to do with SQL
ability. Each candidate was preflighted with a single cheap call before committing to a
paid 50-question run. The measurement discipline isn't only in the harness; it's in not
burning a long run on a model you haven't validated.

---

## What we refused to build

- **LangGraph for its own sake.** The plan said it plainly: if the framework had fought
  the timeline, the hand-rolled state machine was a legitimate *permanent* choice —
  "framework where it earned its place, plain code where it didn't" is itself a maturity
  signal. It happened to fit; that's why it's here.
- **Raising the token cap to flatter reasoning models.** Tempting (4096 tokens would let
  a reasoning model finish), but it changes the baseline and muddies the comparison. We
  kept 1024 and chose non-reasoning models instead — a cleaner control.
- **A hand-tuned cost table for OpenRouter.** The honest cost basis is OpenRouter's own
  reported price, captured from the response — not a number I curate and inevitably let
  drift. The table records the basis and refuses to pretend two bases are comparable.

---

## What's next

The pipeline is now a framework-backed, multi-provider, measured system — and every
number it produces traces to a config and a commit. What it *isn't* yet is observable
from the outside.

- **Step 8** — wire **Langfuse**: a span per stage, a trace per run, and the redaction
  contract enforced so only the presented (redacted) result is ever logged — never raw
  PII, never the raw verified result the harness scores upstream. The trace becomes the
  debugging surface the eval numbers point at.

Step 5 proved a feature was worth nothing; Step 6 proved retrieval pays only where the
schema overflows; Step 7 proves a framework-and-provider swap was worth *exactly zero*
change in behavior — and that proving the zero is the feature. Build the measurement
that can tell you the truth, introduce the framework only once the truth is pinned down,
and the refactor stops being a leap of faith and becomes a thing you can simply check.
