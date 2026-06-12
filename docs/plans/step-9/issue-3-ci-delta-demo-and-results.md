# Issue 3 — CI catches a real prompt-change delta + RESULTS.md (Step 9 DoD)

**Type:** AFK
**Phase:** Step 9 (Operations) — *Prompt-CI/CD, the senior differentiator* · **Step 9 Definition of Done**

## Parent

`docs/plans/step-9/plan-step-9.md`

## What to build

Demonstrate the CI catching a real prompt change: an edit triggers an automated eval run that reports **pass@1/pass@k deltas** against the frozen slice — a showcase artifact for the blog.

- Make a real prompt change; let the workflow run; capture the reported before/after delta (CI catching a regression or confirming an improvement).
- Append a `RESULTS.md` entry with the example before/after delta and full config (model, slice ID, prompt version, date, commit).

## Acceptance criteria

- [ ] A real prompt edit triggers the workflow and reports pass@1/pass@k deltas vs the frozen slice
- [ ] The before/after delta is captured (regression caught or improvement confirmed)
- [ ] `RESULTS.md` records the example delta with full config
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#58](https://github.com/chiajung-wang/nl2sql-eval/issues/58) — the eval workflow.

---

## Tracking

**GitHub:** [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59) · label `agent-ready`, `step-9`

**PR:** _pending_

**Blocked by (GitHub):** [#58](https://github.com/chiajung-wang/nl2sql-eval/issues/58)

**Step 9 set:** [#57](https://github.com/chiajung-wang/nl2sql-eval/issues/57) · [#58](https://github.com/chiajung-wang/nl2sql-eval/issues/58) · [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59)
