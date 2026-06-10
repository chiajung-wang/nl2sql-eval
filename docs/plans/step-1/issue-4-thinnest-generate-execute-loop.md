# Issue 4 — Thinnest generate→execute loop

**Type:** AFK
**Phase:** Step 1 (Foundation) — *Prove the machine runs end-to-end*

## Parent

`docs/plans/step-1/plan-step-1.md`

## What to build

The thinnest possible hand-rolled pipeline: a linear `question → generate → execute → return` path. No guardrails, no retrieval, no self-correction, no framework, one provider called directly.

Includes:
- `generate.py`: a single **direct Anthropic SDK** call producing candidate SQL. The full payments schema is dumped **inline** in the prompt (retrieval is Step 6). Default to a current Claude model (Sonnet 4.x).
- The generation prompt **externalized** as a versioned template in `prompts/` — never inlined in Python (CI diffs `prompts/`).
- `execute.py`: SQLAlchemy execution of the candidate SQL against the payments Postgres db.
- `graph.py`: hand-rolled plain-Python linear wiring `generate → execute → return` — **no loop, no conditional edges yet**.
- Each stage calls the thin obs logging seam from Issue 1.

Scope guard: do not add sqlglot guarding, retrieval, correction, LangGraph, LiteLLM, Langfuse, the harness, or the UI.

## Acceptance criteria

- [ ] `generate.py` calls the Anthropic SDK once and returns candidate SQL, with the schema passed inline.
- [ ] The generation prompt lives as a template in `prompts/`, not inlined in Python.
- [ ] `execute.py` runs the candidate SQL via SQLAlchemy against the payments db and returns the result set.
- [ ] `graph.py` wires `generate → execute → return` linearly with no loop.
- [ ] Each stage emits a structured log through the obs seam.
- [ ] Feeding one question yields candidate SQL that executes and returns rows (correctness is asserted in Issue 5).

## Blocked by

- Issue 1 — Skeleton & tooling
- Issue 2 — Payments Postgres database
