# Issue 2 — eval.yml: run harness on prompt change, post pass@1/pass@k deltas

**Type:** AFK
**Phase:** Step 9 (Operations) — *Prompt-CI/CD, the senior differentiator*

## Parent

`docs/plans/step-9/plan-step-9.md`

## What to build

The senior differentiator, live: a **GitHub Action** that runs the harness on the frozen slice whenever a prompt changes, and posts the **pass@1/pass@k deltas**.

- `.github/workflows/eval.yml`: on change to `prompts/`, run the harness against the **frozen, seeded, stratified** slice and post pass@1/pass@k deltas (PR comment or job summary).
- The slice is seeded and checked into the repo (an explicit ID list), stratified by BIRD difficulty so a delta means a real regression, not sampling variance.
- **Cost guard:** keep the slice small enough that per-push LLM cost is acceptable; document the trade-off.

## Acceptance criteria

- [ ] `.github/workflows/eval.yml` triggers on changes to `prompts/`
- [ ] The workflow runs the harness against the frozen, seeded, stratified slice
- [ ] pass@1/pass@k deltas are posted (PR comment or job summary)
- [ ] A cost guard keeps the slice small; the trade-off is documented
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#57](https://github.com/chiajung-wang/nl2sql-eval/issues/57) — clean prompt templates.

---

## Tracking

**GitHub:** [#58](https://github.com/chiajung-wang/nl2sql-eval/issues/58) · label `agent-ready`, `step-9`

**PR:** _pending_

**Blocked by (GitHub):** [#57](https://github.com/chiajung-wang/nl2sql-eval/issues/57)

**Step 9 set:** [#57](https://github.com/chiajung-wang/nl2sql-eval/issues/57) · [#58](https://github.com/chiajung-wang/nl2sql-eval/issues/58) · [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59)
