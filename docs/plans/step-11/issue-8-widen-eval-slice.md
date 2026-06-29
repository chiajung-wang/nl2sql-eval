# Issue 8 — Widen the evaluation slice (decide the inconclusive nulls)

**Type:** AFK
**Phase:** Step 11 follow-up (Optimization) — *measurement substrate; unblocks every marginal lever*

## Parent

`docs/plans/step-11/plan-step-11.md`

## Motivation (the noise floor is eating the results)

The dev slice is **50 questions** and the stated sampling-noise floor is **~0.05**
(temperature > 0). The model swap (+0.10) clears it comfortably — but **most
other levers Step 11 considered land *inside* that floor on a slice this size**,
so they come back "inconclusive," not decided:

- **FK-only schema enrichment**: 0.420 → 0.400 (**−0.020, within noise**) — moved
  the target bucket the right way (11→8) but couldn't move the headline past
  jitter (#112).
- The `spurious_join` FK-soundness lever was **deferred by construction**: at
  ≤5/50 questions its A/B "would be inconclusive by construction" (#122).
- Adaptive-gate deltas and similar small effects were all read as "within the
  noise floor."

These aren't true negatives — they're **unresolved**. A slice that resolves a
**+0.03** effect would convert several of them from "inconclusive" to "decided,"
and is a *prerequisite* for the table-selection levers (issue-9/issue-10), which
are exactly the marginal-effect regime where a 50-question slice can't
distinguish signal from sampling jitter. **Measurement is the product**
(CLAUDE.md framing) — so widen the substrate before spending effort on levers it
can't measure.

## What to build

A larger / additional **frozen, seeded, stratified** evaluation slice, built the
same disciplined way as the existing ones (`eval/datasets/bird/`,
frozen ID list, stratified by difficulty per the Step-9/Step-11 pattern):

- **Either** enlarge the dev iteration slice **or** add a second stratified dev
  slice (e.g. `step11-dev-wide`) disjoint from `step11-holdout` and the
  prompt-CI slice. Size it for the target resolution: state the chosen N and the
  noise floor it buys (a +0.03 detectable effect needs materially more than 50 q
  — compute and document the target, don't guess).
- **Preserve the dev/held-out separation** (`plan-step-11.md`): the wider slice
  is for *iteration*; `step11-holdout` remains touched only once for the
  generalization claim. If the wider slice overlaps the existing dev slice, keep
  continuity with the committed 0.420 trail (document the relationship).
- **Re-establish the anchors on the wider slice**: re-run the baseline
  (sonnet, `generate/v3`) and the `accuracy` config (gemini-3.5-flash) so future
  levers A/B against a same-slice anchor, not a cross-slice one.
- Respect the **db-level caveat already documented** in `plan-step-11.md`: the
  small-schema pool has few dbs, so this stays *question-level* widening — note
  whether more dbs can be pulled in to reduce per-db concentration.

## Evaluation protocol

- The slice itself ships frozen/seeded/stratified with its ID list committed
  under `eval/datasets/bird/` (CLAUDE.md §5 invariant 9).
- Re-baseline numbers (sonnet + `accuracy` config) on the wider slice go to
  `RESULTS.md` with full config + commit, **strict and BIRD set-semantics**, so
  the new anchor is traceable.
- **Re-test the inconclusive nulls** against the wider slice where cheap (FK-only
  enrichment is the obvious candidate): does −0.020 stay null, or resolve? Record
  the verdict either way.

## Acceptance criteria

- [ ] A wider (or second) frozen/seeded/stratified dev slice committed under
      `eval/datasets/bird/`, disjoint from `step11-holdout`, with its target N
      and resulting noise floor documented
- [ ] dev/held-out separation preserved; held-out still touched only once
- [ ] Baseline (sonnet) and `accuracy` (gemini-3.5-flash) anchors re-established
      on the wider slice and recorded in `RESULTS.md` (strict + BIRD, full config
      + commit)
- [ ] At least one previously-inconclusive null (e.g. FK-only enrichment)
      re-tested on the wider slice and its verdict recorded
- [ ] `uv run pytest` green; lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])**
      the re-baseline runs are paid; prove the slice construction + harness wiring
      offline first, then run with an authorized key/budget

## Out of scope

- Tuning any accuracy lever here (this issue only widens + re-anchors the
  substrate; the levers are issue-9/issue-10).
- Re-running the *full* historical results matrix on the new slice — only the
  anchors plus the cheap inconclusive-null re-test.
- Cross-db routing or multi-db evaluation (PRD non-goal).

## Blocked by

- None hard. Should land **before** issue-9/issue-10 so their marginal effects
  are measurable. Independent of issue-7.

---

## Tracking

**GitHub:** [#133](https://github.com/chiajung-wang/nl2sql-eval/issues/133) · label `agent-ready`, `step-11`

**PR:** _pending_

**Step 11 follow-up set:** #121 · #122 · #132 (named configs) · **#133 (this)** ·
#134 (table-selection root cause) · #135 (explicit table pre-selection)
