# Issue 3 — pass@1→pass@k gap on BIRD + RESULTS.md (Step 5 DoD)

**Type:** AFK
**Phase:** Step 5 (Measured features) — *Self-correction + pass@k* · **Step 5 Definition of Done**

## Parent

`docs/plans/step-5/plan-step-5.md`

## What to build

Run the twin-metric harness over the frozen BIRD slice and produce the **pass@1 → pass@k gap** as a committed result — one of the two sharpest findings in the project.

- Run the slice with correction off (pass@1) and on (pass@k); capture both, the gap, and the added cost/latency.
- Append a `RESULTS.md` row with full config: model, slice ID, prompt version, date, commit, **pass@1**, **pass@k**, the gap, and the cost/latency delta.
- State the finding in plain terms — e.g. "self-correction recovers X% of initial failures at a cost of Y% added latency."

## Acceptance criteria

- [ ] Harness run over the frozen BIRD slice produces pass@1, pass@k, the gap, and added cost/latency
- [ ] `RESULTS.md` row appended with model, slice ID, prompt version, date, commit, pass@1, pass@k, gap, cost/latency
- [ ] The pass@1→pass@k finding is stated plainly (recovery rate vs added cost)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#43](https://github.com/chiajung-wang/nl2sql-eval/issues/43) — the twin-metric harness extension.

---

## Tracking

**GitHub:** [#44](https://github.com/chiajung-wang/nl2sql-eval/issues/44) · label `agent-ready`, `step-5`

**PR:** _pending_

**Blocked by (GitHub):** [#43](https://github.com/chiajung-wang/nl2sql-eval/issues/43)

**Step 5 set:** [#42](https://github.com/chiajung-wang/nl2sql-eval/issues/42) · [#43](https://github.com/chiajung-wang/nl2sql-eval/issues/43) · [#44](https://github.com/chiajung-wang/nl2sql-eval/issues/44)
