# Issue 3 — Thin demo UI that reveals the wrapper (Streamlit, isolated deps)

**Type:** AFK
**Phase:** Step 10 (Amplification) — *Polish & reach* · **Non-negotiable**

## Parent

`docs/plans/step-10/plan-step-10.md`

## What to build

A **thin demo UI** (`apps/demo/`, Streamlit, isolated dep group) that **reveals the wrapper** rather than hiding a chatbot.

- Show the guardrail decision, retry count, cost, and terminal state — the machinery, not a slick chat box.
- Import the **same shared pipeline** the harness uses — no fork, no drift between what is demoed and what is measured.
- Isolate the demo's deps (own dependency group) so it can't conflict with the pipeline core.

## Acceptance criteria

- [ ] `apps/demo/` (Streamlit) imports the same shared pipeline as the harness (no fork)
- [ ] The UI surfaces guardrail decision, retry count, cost, and terminal state
- [ ] Demo dependencies are isolated in their own group; they can't conflict with the core
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- Steps 1–9 (the pipeline the demo reveals). Predecessor: [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59).

---

## Tracking

**GitHub:** [#62](https://github.com/chiajung-wang/nl2sql-eval/issues/62) · label `agent-ready`, `step-10`

**PR:** _pending_

**Blocked by (GitHub):** [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59) (Steps 1–9 complete)

**Step 10 set:** [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60) · [#61](https://github.com/chiajung-wang/nl2sql-eval/issues/61) · [#62](https://github.com/chiajung-wang/nl2sql-eval/issues/62) · [#63](https://github.com/chiajung-wang/nl2sql-eval/issues/63) (#63 optional reach)
