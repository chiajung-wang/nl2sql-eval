# Issue 2 — Order-sensitivity (the `ORDER BY` conditional)

**Type:** AFK
**Phase:** Step 2 (Foundation) — *Prove the scorer is trustworthy before trusting any number it produces*

## Parent

`docs/plans/step-2/plan-step-2.md`

## What to build

The subtle, false-negative-prone canonicalization rule, isolated so it gets the attention it deserves: row order is normalized away **unless** the gold query declares it significant.

Includes:
- In `eval/compare.py`: before comparing, **sort rows** on both sides — **unless** the gold SQL contains a top-level `ORDER BY`, in which case row order is part of correctness and must NOT be sorted away.
- Detect `ORDER BY` via **sqlglot AST parsing — never regex** (CLAUDE.md §4: guardrails and the comparator are deterministic, sqlglot ASTs only; regex for SQL semantics is forbidden). Consider only an order that affects the output (e.g. a top-level `ORDER BY`), not an `ORDER BY` buried in a subquery that doesn't change the final row order.
- Golden-fixture triples covering the rule both ways:
  - gold has `ORDER BY`, candidate returns the **same rows in the wrong order** → **wrong** (order error must be caught).
  - gold has `ORDER BY`, candidate returns the same rows in the **same order** → correct.
  - gold has **no** `ORDER BY`, candidate returns the same rows in a different order → **correct** (order is not significant).

Scope guard: only the ordering rule and its fixtures here. Value-level canonicalization (NULL/float/column/multiset) is Issue 3.

## Acceptance criteria

- [ ] When the gold SQL has no significant `ORDER BY`, row order differences do not change the verdict.
- [ ] When the gold SQL has a significant `ORDER BY`, a same-rows/wrong-order candidate is judged **wrong**.
- [ ] `ORDER BY` detection uses sqlglot AST parsing, not regex or string scanning.
- [ ] Golden-fixture triples cover all three cases above and pass.
- [ ] `uv run pytest` passes; lint/format clean.

## Blocked by

- Issue 1 — Comparator core & golden-fixture harness.

---

## Tracking

**GitHub:** [#12](https://github.com/chiajung-wang/nl2sql-eval/issues/12) · label `agent-ready`, `step-2`

**Blocked by (GitHub):** #11

**Step 2 set:** [#11](https://github.com/chiajung-wang/nl2sql-eval/issues/11) · [#12](https://github.com/chiajung-wang/nl2sql-eval/issues/12) · [#13](https://github.com/chiajung-wang/nl2sql-eval/issues/13) · [#14](https://github.com/chiajung-wang/nl2sql-eval/issues/14)
