# Issue 3 — First BIRD pass@1 + RESULTS.md (Phase 1 DoD)

**Type:** AFK
**Phase:** Step 3 (Foundation) — *Produce the first trustworthy measured claim* — **PHASE 1 DEFINITION OF DONE**

## Parent

`docs/plans/step-3/plan-step-3.md`

## What to build

The **Phase 1 Definition of Done**: the first real, trustworthy pass@1 number on BIRD — the project's thesis made concrete, a measured claim rather than a working toy.

Includes:
- **Run the batch harness (Issue 1) over the frozen small-schema BIRD slice (Issue 2)**, producing **pass@1** from the now-validated Step-2 comparator.
- **Append the mandated row to `RESULTS.md`**: **date, model, slice ID, prompt version, commit, pass@1**, plus a one-line note labeling it the **naive schema-dump baseline, small-schema slice** (CLAUDE.md §6). The results log **starts here and is now mandatory**: from this step on, no step's done-when is met until its number is in `RESULTS.md` with full config.

Framing (important): this pass@1 is the naive-schema-dump **baseline** — the "before" that Step 6's retrieval will lift. A modest number here is a *feature* of the narrative, not a failure, as long as it's labeled as such.

## Acceptance criteria

- [ ] The harness runs over the frozen BIRD slice and emits a pass@1 number.
- [ ] `RESULTS.md` has a row with date, model, slice ID, prompt version, commit, and the pass@1 number.
- [ ] The entry is explicitly labeled the naive schema-dump baseline on the small-schema slice.
- [ ] The number is reproducible from the checked-in slice ID list + config.
- [ ] `uv run pytest` passes; lint/format clean.

## Blocked by

- Issue 1 — Batch harness + metrics (#26).
- Issue 2 — BIRD loader + frozen small-schema slice (#27).

---

## Tracking

**GitHub:** [#28](https://github.com/chiajung-wang/nl2sql-eval/issues/28) · label `agent-ready`, `step-3`

**Blocked by (GitHub):** #26, #27

**Step 3 set:** [#26](https://github.com/chiajung-wang/nl2sql-eval/issues/26) · [#27](https://github.com/chiajung-wang/nl2sql-eval/issues/27) · [#28](https://github.com/chiajung-wang/nl2sql-eval/issues/28)
