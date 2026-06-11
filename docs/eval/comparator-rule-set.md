# The comparator rule set — and how it aligns with BIRD

> *"Here's how I know my evaluator is correct."*

This is the committed, defensible statement of how `eval/compare.py` decides
whether a candidate query's result is correct. It closes Step 2 (Issue 4): every
rule is reconciled against the **official BIRD evaluator**, deliberate
divergences are recorded with their rationale, and each decision below is
**proven by a golden-fixture triple**, not asserted.

A scorer you cannot defend invalidates every number it produces. So this document
exists, and the fixture under `fixtures/golden_compare/` must pass in its
entirety (CLAUDE.md §8, §10).

## How correctness is decided

`compare(gold_result, candidate_result, gold_sql, *, rules=DEFAULT_RULES)`
canonicalizes **both** sides through an ordered list of named rules, then returns
`correct` iff the canonicalized rows are equal. Comparison is on result-set
**values**, never the SQL string (CLAUDE.md §5.1, §7). Because every rule is
applied identically to gold and candidate, a canonicalization can only let two
equally-correct queries compare equal — it can never make a wrong answer look
right.

The default pipeline, in order:

```
DEFAULT_RULES = (column_position, null_sentinel, float_tolerance, order_insensitive, exact)
```

| Order | Rule | What it does |
|------:|------|--------------|
| 1 | `column_position` | Match columns by position, not label — an alias/rename can't fail a correct query; transposed values still fail. |
| 2 | `null_sentinel` | Normalize every SQL `NULL` to one sentinel, distinct from `0`/`""`/`"None"`, so NULLs compare consistently and are orderable. |
| 3 | `float_tolerance` | Round floats/`Decimal`s to `FLOAT_DECIMALS = 6` places; `bool` untouched. |
| 4 | `order_insensitive` | Sort rows away **unless** the gold SQL has a top-level `ORDER BY` (sqlglot AST, never regex) — then row order is the answer. |
| 5 | `exact` | Identity; names the final value-equality comparison. |

**Ordering is deliberate.** Value normalization (1–3) runs *before*
`order_insensitive` (4): that rule sorts rows by their stringified cells, so
floats must already be rounded and NULLs normalized, or the same logical rows
could sort differently on the two sides and a correct answer would be judged
wrong.

**Multiset by omission.** There is intentionally **no de-dup rule** in the
default pipeline, so two results differing only in row multiplicity (the classic
`COUNT` vs `COUNT DISTINCT` bug) stay distinct. Duplicate-sensitivity is the
default *because* the `set` rule is absent from `DEFAULT_RULES`.

## The reference: BIRD's official evaluator

The BIRD evaluator decides correctness with a single line
(`AlibabaResearch/DAMO-ConvAI` → `bird/llm/src/evaluation.py`):

```python
if set(predicted_res) == set(ground_truth_res):
    res = 1
```

over the rows from `cursor.fetchall()`. That one `set()` makes BIRD:

- **order-insensitive — always**, even when the gold query has an `ORDER BY`;
- **duplicate-collapsing** (multiplicity is invisible); and
- **exact on values** — no float tolerance.

We reproduce exactly this verdict on demand via the opt-in **`BIRD_RULES`**:

```
BIRD_RULES = (column_position, set, exact)
```

where the `set` rule de-duplicates and order-normalizes rows in one step — the
BIRD primitive. (`float_tolerance` and `null_sentinel` are omitted: BIRD compares
floats exactly, and the NULL sentinel is a bijective internal relabel that would
not change any verdict.)

## Per-rule audit against BIRD

| Comparator behavior | BIRD behavior | Verdict | Why |
|---------------------|---------------|---------|-----|
| `column_position` (positional, label-blind) | `fetchall()` tuples carry no labels; positional | **Aligned** | Both match by position; a rename can't fail a correct query under either. |
| `null_sentinel` | raw `None` inside `set()` | **Aligned** (mechanism differs) | Sentinel ⇔ `None` is bijective; `NULL` matches `NULL`, never equals `0`, under both. |
| empty-result handling | `set()==set()` | **Aligned** | Both-empty → correct; empty vs non-empty → incorrect, both ways. |
| `float_tolerance` (6 dp) | exact float equality | **Divergent — we are *more lenient*** | BIRD's exact compare is a **false-negative** machine: two equal-to-9-digits `AVG`s are judged different. We round to 6 dp so FP representation noise from equivalent computations isn't counted as wrong. This is the *only* axis where we may call correct something BIRD calls wrong; the gap is bounded by `10⁻⁶`. |
| `order_insensitive` gated on gold `ORDER BY` | order-insensitive always | **Divergent — we are *stricter*** | When the gold declares a top-level `ORDER BY`, the order **is** the answer ("list X by Y"). BIRD's `set()` can't see a broken `ORDER BY`; we make order significant only when the gold asserts it, catching a real error class BIRD masks. |
| multiset (no de-dup) | `set()` collapses duplicates | **Divergent — we are *stricter*** | Row multiplicity is semantically meaningful (`COUNT` vs `COUNT DISTINCT`, `GROUP BY` cardinality). BIRD's set-comparison is a documented blind spot; we preserve duplicates so multiplicity bugs are caught. |

### Net effect

Three deliberate divergences. On **order** and **multiplicity** we are *stricter*
than BIRD — we will reject candidates BIRD accepts, catching real bugs its
set-comparison hides. On **float noise** we are *more lenient* — we accept
candidates BIRD rejects for insignificant precision. Everything else is aligned.

Practically: `DEFAULT_RULES` is a documented **refinement** of BIRD, not a
contradiction of it. For strict leaderboard parity, score the same results a
second time with `rules=BIRD_RULES`; the difference between the two pass-rates is
exactly the set of verdicts BIRD's `set()` comparison masks — a quantity worth
reporting, not hiding.

## How each decision is proven

`fixtures/golden_compare/bird_alignment.json` pins every row of the audit. Each
divergence is a **pair** of triples on identical data — one under `BIRD_RULES`
(BIRD's verdict), one under `DEFAULT_RULES` (ours):

| Decision | BIRD-rules case | Default-rules case |
|----------|-----------------|--------------------|
| Multiplicity | `divergence-multiset__bird-collapses-duplicates` → correct | `divergence-multiset__ours-rejects-duplicate-loss` → incorrect |
| Order | `divergence-order__bird-ignores-order-by` → correct | `divergence-order__ours-rejects-reorder-when-gold-orders` → incorrect |
| Float | `divergence-float__bird-rejects-precision-noise` → incorrect | `divergence-float__ours-accepts-within-tolerance` → correct |
| NULL | `aligned-null__matches-under-bird`, `aligned-null__never-equals-zero-under-bird` | (default NULL behavior pinned in `value_shape.json`) |
| Empty | `aligned-empty__both-empty-correct-under-bird`, `aligned-empty__empty-vs-nonempty-incorrect-under-bird` | — |
| Columns | `aligned-column-position__rename-matches-under-bird` | (`value_shape.json`) |

All triples are loaded and asserted automatically by `tests/test_compare.py`;
adding a case is exercised with no test edits. The divergence is also pinned as
unit tests (`test_default_and_bird_rules_diverge_on_the_same_data`,
`test_bird_rules_have_no_float_tolerance`).

## Scope

No `RESULTS.md` benchmark entry yet — that discipline begins at Step 3, when the
harness produces real numbers. This document and its green fixture are the Step 2
Definition of Done: the comparator is proven trustworthy *before* any number is
trusted to it.
