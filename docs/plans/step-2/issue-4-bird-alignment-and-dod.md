# Issue 4 — BIRD alignment & Definition of Done

**Type:** AFK
**Phase:** Step 2 (Foundation) — *Prove the scorer is trustworthy before trusting any number it produces*

## Parent

`docs/plans/step-2/plan-step-2.md`

## What to build

The slice that closes Step 2: reconcile the comparator's ambiguous decisions with BIRD's official evaluator so numbers stay leaderboard-comparable, document the committed rule set, and confirm the **entire** golden fixture passes. This is the plan's "done when."

Includes:
- An audit of each canonicalization rule (ordering, column-position, NULL, float tolerance, multiset, empty result) against **BIRD's official evaluator** behavior. Where the comparator was ambiguous, align it with BIRD; where we deliberately diverge, record *why*.
- A short, committed write-up of the final rule set — the explicit, defensible statement of how the scorer decides correctness (the "here's how I know my evaluator is correct" reference for the blog).
- Any additional fixture triples needed to lock in the BIRD-aligned decisions, so "BIRD-aligned" is proven by the fixture rather than asserted.
- Confirm `compare.py` passes its **entire** golden fixture — the Step 2 Definition of Done.

No `RESULTS.md` benchmark entry yet (that discipline starts at Step 3); but the fixture and its green status are committed as the defensible artifact.

## Acceptance criteria

- [ ] Each canonicalization rule is reconciled with BIRD's official evaluator; deliberate divergences are documented with rationale.
- [ ] The final comparator rule set is written up and committed.
- [ ] Fixture triples exist that pin the BIRD-aligned decisions (claim is proven, not asserted).
- [ ] `compare.py` passes its **entire** golden fixture — Step 2 Definition of Done met.
- [ ] `uv run pytest` passes; lint/format clean.

## Blocked by

- Issue 2 — Order-sensitivity (the `ORDER BY` conditional).
- Issue 3 — Value & shape canonicalization.

---

## Tracking

**GitHub:** [#14](https://github.com/chiajung-wang/nl2sql-eval/issues/14) · label `agent-ready`, `step-2`

**Blocked by (GitHub):** #12, #13

**Step 2 set:** [#11](https://github.com/chiajung-wang/nl2sql-eval/issues/11) · [#12](https://github.com/chiajung-wang/nl2sql-eval/issues/12) · [#13](https://github.com/chiajung-wang/nl2sql-eval/issues/13) · [#14](https://github.com/chiajung-wang/nl2sql-eval/issues/14)
