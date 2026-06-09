# Plan — Step 7: Swap in LangGraph + LiteLLM; cross-provider table

**Phase:** Framework / provider (only AFTER logic is proven)
**Headline:** Introduce the framework where it earns its place — and use the harness to prove the refactor changed nothing.

## Goal
Refactor the now-proven hand-rolled loop into **LangGraph**, swap the direct LLM call for **LiteLLM** (multi-provider), and produce a **cross-provider comparison table**. Deferred to here deliberately so framework/provider churn never masked logic bugs during Steps 1–6.

## Prerequisites
- Steps 1–6 (a fully working, measured pipeline). The logic must be proven first.

## What to build
1. **LangGraph refactor** (`pipeline/graph.py`) — re-express the state machine as LangGraph nodes + conditional edges. The architecture already *is* a graph with conditional transitions (correction loop, retrieval re-trigger, terminal-state branching), so this is a genuine fit. (If LangGraph friction threatens the timeline, the hand-rolled state machine remains a legitimate permanent choice — "framework where it earned its place, plain code where it didn't" is itself a maturity signal.)
2. **LiteLLM swap** (`llm/`) — replace the direct single-provider call with the LiteLLM abstraction. Note this mirrors JKOPay's actual "LiteLLM Gateway" stack. Makes multi-provider comparison trivial.
3. **Cross-provider comparison** — run the harness across providers/models and produce a table of **accuracy × cost × latency** per model. This turns "model selection / cost-latency-quality trade-offs" (a JKOPay JD requirement) into a concrete eval artifact.

## Done when
- **Same-or-better numbers post-refactor** — the harness proves the LangGraph/LiteLLM swap was behavior-preserving (this is exactly what the harness is for).
- A multi-provider results table exists.

## Results log
Append the **post-refactor numbers** (showing parity with pre-refactor) and the **cross-provider table** (model, accuracy, cost, latency) with config + commit.

## Pitfalls
- If numbers regress after the swap, the refactor broke something — investigate before proceeding; don't accept silent regressions.
- Don't let LangGraph API churn derail the timeline; hand-rolled is a defensible fallback.
- The git history (hand-rolled → framework) is itself a narrative asset — "I introduced LangGraph when the state machine earned it." Don't squash it away.
