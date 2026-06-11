# Issue 1 — Batch harness + metrics, proven on payments gold

**Type:** AFK
**Phase:** Step 3 (Foundation) — *Produce the first trustworthy measured claim*

## Parent

`docs/plans/step-3/plan-step-3.md`

## What to build

The batch harness that turns the Step-1 pipeline + Step-2 comparator into a repeatable measurement job — proven end-to-end against trusted ground (the payments verified gold set) **before** any BIRD data is involved. This is the thinnest end-to-end slice of the harness: it scores a known set correctly before we point it at questions we don't know cold.

Includes:
- **`eval/harness.py`** — a batch runner: iterate a test set, invoke the **shared-import** pipeline (never a copy — no drift from the demo), score each result via `eval/compare.py`, and bucket each run into exactly one terminal state. **Batch-capable, offline, repeatable** by design — invokable as a job, not only behind the demo (this is what enables prompt-CI later).
- **`eval/metrics.py`** — accuracy aggregation and the **terminal-state classifier** (lives here, not in `state.py`, per CLAUDE.md §3). Emit **pass@1** — with no self-correction yet, pass@1 is the only meaningful metric this step.
- **Validation on the payments gold set** (`eval/datasets/payments/`), whose gold answers we trust cold: if the harness can't score those correctly, it has no business scoring BIRD.

Scope guard: no BIRD loading here (Issue 2), no `RESULTS.md` number yet (Issue 3). Never string-compare SQL — only result sets via `compare.py` (CLAUDE.md §5.1, §7).

## Acceptance criteria

- [ ] `eval/harness.py` runs a batch over a test set, invoking the shared-import pipeline (not a duplicated copy) and scoring each via `eval/compare.py`.
- [ ] `eval/metrics.py` holds the terminal-state classifier (not `state.py`) and aggregates pass@1.
- [ ] Every run buckets into exactly one terminal state; pass@1 is computed over the batch.
- [ ] Verified end-to-end on the payments gold set (trusted ground), runnable as an offline job.
- [ ] `uv run pytest` passes; lint/format clean.

## Blocked by

None — can start immediately (Step 1 pipeline and Step 2 comparator are merged).

---

## Tracking

**GitHub:** [#26](https://github.com/chiajung-wang/nl2sql-eval/issues/26) · label `agent-ready`, `step-3`

**Blocked by (GitHub):** None — can start immediately

**Step 3 set:** [#26](https://github.com/chiajung-wang/nl2sql-eval/issues/26) · [#27](https://github.com/chiajung-wang/nl2sql-eval/issues/27) · [#28](https://github.com/chiajung-wang/nl2sql-eval/issues/28)
