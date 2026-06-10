# Issue 3 — Value & shape canonicalization

**Type:** AFK
**Phase:** Step 2 (Foundation) — *Prove the scorer is trustworthy before trusting any number it produces*

## Parent

`docs/plans/step-2/plan-step-2.md`

## What to build

The value- and shape-level canonicalization rules that let two *differently-written-but-equally-correct* queries compare equal, while still catching real semantic errors. Each rule lands with golden-fixture triples that prove it.

Includes (all in `eval/compare.py`, all deterministic, all configurable + logged):
- **Column matching by position, not name** — aliases/renames/reordered output column *labels* must not fail a correct query; columns are matched positionally.
- **NULL handling** — normalize NULLs to a single sentinel so they compare consistently across both sides.
- **Float tolerance** — round/compare floats to a fixed tolerance so insignificant precision differences don't cause false negatives.
- **Duplicate rows = multiset semantics by default** — keep duplicates so a `COUNT` vs `COUNT DISTINCT` difference (different row multiplicities) is caught as a **real error**, not silently collapsed to a set.

Golden-fixture triples covering each rule, including at least:
- correct query with renamed/repositioned columns → correct (positional match).
- NULL-sentinel normalization → correct where it should be.
- within-tolerance float difference → correct; out-of-tolerance → wrong.
- multiset case where set-semantics would wrongly pass (e.g. `COUNT` vs `COUNT DISTINCT`) → **wrong**.

Scope guard: ordering is Issue 2; do not re-implement it here. BIRD reconciliation and final whole-fixture sign-off are Issue 4.

## Acceptance criteria

- [ ] Columns are matched by position; an alias/rename/reposition does not fail an otherwise-correct query.
- [ ] NULLs are normalized to a sentinel and compare consistently.
- [ ] Float comparison uses a fixed tolerance; within-tolerance differences pass, out-of-tolerance fail.
- [ ] Duplicate rows use multiset semantics; a `COUNT` vs `COUNT DISTINCT` style multiplicity difference is judged **wrong**.
- [ ] Golden-fixture triples cover each rule (positional columns, NULL sentinel, float tolerance pass+fail, multiset) and pass.
- [ ] `uv run pytest` passes; lint/format clean.

## Blocked by

- Issue 1 — Comparator core & golden-fixture harness.

(Can proceed in parallel with Issue 2; both extend the Issue 1 core independently.)

---

## Tracking

**GitHub:** [#13](https://github.com/chiajung-wang/nl2sql-eval/issues/13) · label `agent-ready`, `step-2`

**Blocked by (GitHub):** #11

**Step 2 set:** [#11](https://github.com/chiajung-wang/nl2sql-eval/issues/11) · [#12](https://github.com/chiajung-wang/nl2sql-eval/issues/12) · [#13](https://github.com/chiajung-wang/nl2sql-eval/issues/13) · [#14](https://github.com/chiajung-wang/nl2sql-eval/issues/14)
