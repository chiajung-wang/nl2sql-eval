# Plan — Step 1: Skeleton + payments db + thinnest loop

**Phase:** Foundation
**Headline:** Prove the machine runs end-to-end.

## Goal
Stand up the repo and the thinnest possible hand-rolled pipeline: `question → direct LLM call → SQL → execute → return`. No guardrails, no retrieval, no self-correction, no framework, one provider called directly.

## Prerequisites
- None (this is the start).

## What to build
1. **Repo skeleton** with `uv` (`pyproject.toml`), the structure from PRD §8. Stub empty modules so imports resolve.
2. **Payments schema (Postgres)** — DDL + seed data: `users`, `merchants`, `transactions`, `payment_methods`, `refunds`, `disputes`, `ledger`. Include obvious PII columns (e.g. `users.email`) and a write-sensitive `ledger` — these motivate later guardrails/redaction. Keep volume small but realistic.
3. **Thinnest loop** (`pipeline/`, hand-rolled plain Python):
   - `generate.py`: one direct call to a single provider's SDK, schema passed inline (full dump is fine here — retrieval comes in Step 6).
   - `execute.py`: SQLAlchemy execution against Postgres.
   - `graph.py`: linear `generate → execute → return` (no loop yet).
   - `state.py`: the run-state dataclass + the **terminal-state enum** (define the full enum now even though only `success`/`execution_error_final` are reachable yet).
4. **Thin obs seam**: add a no-op/structured-logging hook at each stage now (instrument-as-you-build), not wired to Langfuse yet.
5. A few hand-written payments questions with answers you know cold (these seed the Step 3 trusted ground).

## Keep out (resist scope creep)
sqlglot guardrails, retrieval, correction loop, LangGraph, LiteLLM, Langfuse, the harness, the UI. `sqlglot` may be installed (stable) but is not yet used for guarding.

## Done when
One hand-written payments question returns a **correct** result end-to-end through the loop.

## Results log
Not yet — no benchmark number to record. (Results-log discipline starts at Step 3.) You may informally note which hand-written questions pass.

## Pitfalls
- Don't perfect the agent. A modest generator is fine; the wrapper is the product.
- Define the **full** terminal-state enum now so later steps don't reshape `state.py`.
- Keep the obs seam thin — a logging interface, not Langfuse integration.
