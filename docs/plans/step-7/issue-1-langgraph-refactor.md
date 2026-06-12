# Issue 1 — LangGraph refactor (harness proves parity)

**Type:** AFK
**Phase:** Step 7 (Framework / provider) — *only AFTER logic is proven*

## Parent

`docs/plans/step-7/plan-step-7.md`

## What to build

Refactor the proven hand-rolled state machine into **LangGraph** — and use the harness to prove the refactor changed nothing.

- Re-express the pipeline as LangGraph nodes + conditional edges: the architecture already *is* a graph (correction loop, retrieval re-trigger, terminal-state branching), so this is a genuine fit.
- Keep the two pipeline exits (raw verified result; presented/redacted result) and all terminal states intact.
- Run the harness before and after; the numbers must match (behavior-preserving refactor — exactly what the harness is for).
- If LangGraph friction threatens the timeline, the hand-rolled state machine remains a legitimate permanent choice; document the call either way ("framework where it earned its place, plain code where it didn't" is itself a maturity signal).

## Acceptance criteria

- [ ] Pipeline re-expressed as LangGraph nodes + conditional edges (correction loop, re-trigger, terminal branching preserved)
- [ ] Both pipeline exits and all terminal states unchanged
- [ ] Harness shows same-or-better numbers post-refactor (parity proven, not assumed)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- Steps 1–6 (a fully working, measured pipeline). The logic must be proven first. Direct predecessor: [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49).

---

## Tracking

**GitHub:** [#50](https://github.com/chiajung-wang/nl2sql-eval/issues/50) · label `agent-ready`, `step-7`

**PR:** _pending_

**Blocked by (GitHub):** [#49](https://github.com/chiajung-wang/nl2sql-eval/issues/49) (Steps 1–6 complete)

**Step 7 set:** [#50](https://github.com/chiajung-wang/nl2sql-eval/issues/50) · [#51](https://github.com/chiajung-wang/nl2sql-eval/issues/51) · [#52](https://github.com/chiajung-wang/nl2sql-eval/issues/52)
