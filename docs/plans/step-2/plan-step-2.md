# Plan — Step 2: `compare.py` + golden fixture

**Phase:** Foundation (measurement apparatus)
**Headline:** Prove the scorer is trustworthy *before* trusting any number it produces.

## Goal
Build the result-set comparator with explicit canonicalization, and a checked-in **golden fixture** that proves the canonicalization is correct. A number from an unvalidated scorer is worse than no number — this step is the precondition for Step 3 meaning anything.

## Prerequisites
- Step 1 (a loop that produces result sets to compare).

## What to build
1. **`eval/compare.py`** — canonicalize both result sets, then compare. Rules (commit these explicitly, make them configurable, log per comparison):
   - **Row ordering**: sort rows before comparing **unless** the gold SQL contains `ORDER BY` — in which case order is part of correctness and must NOT be sorted away.
   - **Column matching**: by **position**, not name (aliases/renames must not fail a correct query).
   - **NULL handling**: normalize to a sentinel.
   - **Float tolerance**: round to a fixed tolerance.
   - **Duplicates**: **multiset** semantics by default (so `COUNT` vs `COUNT DISTINCT` differences are caught as real errors).
   - **Empty result**: handled as a distinct, correct-able case.
   - **BIRD alignment**: where ambiguous, align with BIRD's official evaluator so numbers stay leaderboard-comparable.
2. **`fixtures/golden_compare/`** — a **named deliverable**, not throwaway test data. Hand-built `(gold_result, candidate_result, expected_verdict)` triples covering *each* hard case above: order with/without `ORDER BY`, multiset vs set, NULL sentinel, float tolerance, column rename/reposition, empty result. This fixture is what you point at in interviews ("here's how I know my scorer is correct").
3. **`tests/`** for `compare.py` driven by the fixture.

## Done when
`compare.py` passes its **entire** golden fixture.

## Results log
Not a benchmark number yet, but **commit the fixture and its pass status**. The fixture itself is a defensible artifact; reference it in the blog's "how I know my evaluator is correct" section.

## Pitfalls
- The `ORDER BY` conditional is the subtle one — getting it wrong creates false negatives (sorting away real order errors) or false positives.
- Budget real time here; this is undersized if treated as a quick afternoon. It's the module that can silently invalidate every reported number.
- "BIRD-aligned" is an assertion until the fixture proves it.
