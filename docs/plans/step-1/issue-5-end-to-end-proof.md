# Issue 5 — End-to-end proof (Step 1 Definition of Done)

**Type:** AFK
**Phase:** Step 1 (Foundation) — *Prove the machine runs end-to-end*

## Parent

`docs/plans/step-1/plan-step-1.md`

## What to build

The slice that closes Step 1: run a seed question through the linear loop and confirm it returns a **correct** result. This is the plan's "done when."

Includes:
- A small entrypoint (CLI or script) that takes a question from the Issue 3 seed set, runs it through the `graph.py` loop, and prints the returned result set.
- A manual/scripted check comparing the returned result against the known-correct gold answer for at least one seed question.
- Reachable terminal states wired through: a clean correct run buckets as `success`; a failed execution buckets as `execution_error_final`. (Only these two are reachable in Step 1; the full enum already exists from Issue 1.)

No results-log entry yet — `RESULTS.md` discipline starts at Step 3. You may informally note which hand-written questions pass.

## Acceptance criteria

- [ ] An entrypoint runs a seed question end-to-end through `generate → execute → return`.
- [ ] At least one hand-written payments question returns a result matching its verified gold answer.
- [ ] A correct run reports terminal state `success`; an execution failure reports `execution_error_final`.
- [ ] The run emits per-stage structured logs via the obs seam.

## Blocked by

- Issue 3 — Verified question seed set
- Issue 4 — Thinnest generate→execute loop
