---
title: "Step 2 — Proving the Scorer"
subtitle: "A canonicalized result-set comparator, proven against a golden fixture — and three places it disagrees with the BIRD evaluator on purpose"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 2
date: 2026-06-11
author: Chia-Jung Wang
tags: [llm, nl2sql, evaluation, sqlglot, bird, testing]
---

# Step 2 — Proving the Scorer

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness around it is the *product*. Step 1 proved the machine runs end-to-end.
> But it scored answers with a deliberate stand-in — a value-level check we labeled,
> in the code, as temporary. Step 2 builds the real thing: the comparator every
> future number will rest on, and the proof that it's correct.

Every accuracy number this project ever reports is a claim made by one function:
*was this result right?* If that function is wrong, every number downstream is
noise wearing a lab coat. So before the harness scores a single benchmark
question, the comparator has to be **proven** — not plausible, not "passes a few
tests," but pinned against a fixture of cases whose verdicts we know cold.

That is the whole of Step 2. No benchmark runs. No leaderboard. One file —
`eval/compare.py` — and the apparatus that proves it.

---

## Why the comparator is the hard part

Here is the rookie error, and it's domain rule number one:

> Execution accuracy via canonicalized result-set comparison, **never SQL
> string-match.** Two different queries can be equally correct.

`SELECT name FROM t WHERE country='US'` and `SELECT name FROM t WHERE country = 'US' ORDER BY id`
might return the same rows. Two analysts answering "how many US users?" might
label the column `n` or `us_user_count`. One might return `Decimal('42.666667')`,
another the float `42.66666673`. A naive `==` rejects correct answers; a `set()`
that's too loose accepts wrong ones. The comparator lives in the narrow band
between false negatives and false positives, and **where exactly it draws those
lines is a series of judgment calls that have to be made explicit and defended.**

That's the trap: a comparator's bugs are silent. It never crashes. It just quietly
miscounts, and you ship a number that's off by some unknown amount in some unknown
direction. The only defense is to make every decision it makes legible and pinned.

---

## The shape: a pipeline of rules, applied to both sides

The comparator is not a big `if/else`. It's an ordered list of named
**canonicalization rules**, each a small transform from one result set to a
canonical form. `compare()` runs the chosen rules over *both* the gold and the
candidate, then asks one question:

```python
# eval/compare.py (trimmed)
for name in rules:
    gold = _RULES[name](gold, context)
    candidate = _RULES[name](candidate, context)

if gold.rows == candidate.rows:
    verdict = Verdict.CORRECT
```

One invariant makes the whole design safe, and it's worth saying slowly:

> A rule is applied to **both** sides identically. So a canonicalization can only
> ever let two equally-correct answers *match* — it can never make a wrong answer
> look right.

Sorting rows, rounding floats, blanking column labels — each is a transform that
treats gold and candidate the same way. A rule that "helped" one side would break
this and could launder a wrong answer; no rule is allowed to. Everything the
comparator does is a transform you apply to both photographs before you check if
they're the same picture.

Rules register themselves by name:

```python
@register_rule("order_insensitive")
def _order_insensitive(result, ctx): ...
```

…which means each layer of Step 2 added a rule *without touching `compare()`*. The
behavior of the scorer is then declared in exactly one place — a tuple — so you can
read the whole policy at a glance:

```python
DEFAULT_RULES = (
    "column_position",   # match by position, not by column label
    "null_sentinel",     # every NULL collapses to one sentinel
    "float_tolerance",   # round to 6 decimals
    "order_insensitive", # sort rows away — unless the gold declares an ORDER BY
    "exact",             # the final value-equality comparison
)
```

If you read nothing else in `compare.py`, read that tuple. It *is* the scorer.

Step 2 built it in four slices. Each is one rule and the fixture cases that prove
it.

### 1. The core — and the proof ships *with* it

The first slice is the pipeline skeleton, the trivial `exact` rule, and — equally
important — the **golden fixture** and the test that runs it. The fixture is a set
of `(gold, candidate, expected_verdict)` triples; the test loads every one and
asserts `compare()` reproduces the verdict:

```python
# tests/test_compare.py
@pytest.mark.parametrize("case", GOLDEN_CASES)
def test_golden_compare(case):
    result = compare(case["gold_result"], case["candidate_result"],
                     case.get("gold_sql", ""), rules=...)
    assert result.verdict.value == case["expected_verdict"]
```

The fixture *is* the deliverable. Adding a triple is exercised automatically — no
test edits — so the fixture is the living definition of "correct," and a regression
in the scorer shows up as a failing, named case rather than a silently shifted
number.

Two small decisions in the core pay off later. The **empty result set** is its own
case — two empty results compare *correct* (a legitimately empty answer), empty vs
non-empty compares *incorrect* (emptiness is never auto-correct). And the
comparator logs its verdict, the rules it applied, and the gold SQL — but **never
the rows**, because it runs upstream of redaction and raw rows can carry PII.
Scoring sees the real values; the logs never do.

### 2. Order matters — but only when the gold says so

This is the subtle one, and it's where most evaluators are quietly wrong in *both*
directions. Most queries are unordered: "list the merchants" doesn't care about row
order, so a candidate returning the same rows in a different sequence is correct,
and the comparator must sort the difference away. But "list the top 5 merchants **by
revenue**" — there the order *is* the answer, and a wrong order is a wrong answer.

So order-sensitivity is **gated on the gold query**: row order matters only when the
gold SQL declares a top-level `ORDER BY`. And "top-level" is doing real work —
detected from the sqlglot AST, never a regex:

```python
def _gold_order_is_significant(gold_sql: str) -> bool:
    expression = sqlglot.parse_one(gold_sql)
    while isinstance(expression, exp.Subquery):   # unwrap (SELECT ... )
        expression = expression.this
    return expression.args.get("order") is not None
```

An `ORDER BY` buried in a subquery, a derived table, or a CTE body doesn't affect
the final row order — and because sqlglot attaches `order` to the *node it belongs
to*, an inner `ORDER BY` lives on the inner node and is correctly ignored. A regex
scanning for the string `ORDER BY` would false-positive on every one of those, and
on the literal `WHERE label = 'ORDER BY x'`. This is exactly why the project bans
regex for SQL semantics: **understanding SQL is the parser's job.** The fixture pins
all of it — set operations, parenthesized whole queries, CTEs, and an unparseable
gold that falls back to order-insensitive rather than guessing.

### 3. Values and shape: aliases, NULLs, floats — and the duplicate you must keep

The third slice is four decisions about *values*:

- **Columns match by position, not name.** A correct query that labels a column
  `customer` instead of `name` must not fail; a query that *transposes* values
  between two columns still must.
- **NULLs normalize to one sentinel**, distinct from `0`, `""`, and the string
  `"None"` — so a NULL compares consistently and never silently equals a real
  value.
- **Floats round to six decimals.** An `AVG` differing in the ninth digit is
  precision noise, not a wrong answer. (A `bool` is technically an `int`, so it's
  explicitly left alone rather than rounded to 0/1.)

And the one that's a decision *by omission*:

- **Duplicate rows are kept.** There is deliberately no de-dup rule. Two results
  that differ only in row multiplicity — the classic `COUNT(*)` vs
  `COUNT(DISTINCT ...)` bug — stay distinct and compare *incorrect*. Multiset
  semantics aren't something we added; they're what you get when you *don't*
  collapse to a set. We'll come back to why that omission is the whole ballgame.

Pipeline *order* turns out to matter here, and it's the kind of bug that would
never show up in a casual test. Value normalization runs **before**
`order_insensitive`, because the sort sorts rows by their stringified cells — so
floats have to be rounded and NULLs normalized *first*, or the same logical rows
could sort into different positions on the two sides and a correct answer would be
judged wrong. The fix is one line of ordering in the `DEFAULT_RULES` tuple; finding
it is the value of building the pipeline as an explicit, inspectable sequence.

### 4. Aligning with BIRD — and disagreeing with it on purpose

BIRD is the public benchmark this project will report against, so our scorer has to
be legible *relative to BIRD's*. Here is the entirety of BIRD's official evaluator:

```python
# AlibabaResearch/DAMO-ConvAI : bird/llm/src/evaluation.py
if set(predicted_res) == set(ground_truth_res):
    res = 1
```

One line. That single `set()` quietly makes three decisions at once: BIRD is
**order-insensitive always** (even when the gold has an `ORDER BY`),
**duplicate-collapsing** (multiplicity is invisible), and **exact on values** (no
float tolerance). Our default comparator deliberately differs on all three — and
the point of the final slice is to *write down* each divergence with its rationale,
and to *prove* it rather than assert it.

| Our rule | BIRD | We are… | Why |
|---|---|---|---|
| column position, NULL, empty | same | **aligned** | nothing to reconcile |
| `float_tolerance` (6 dp) | exact equality | **more lenient** | BIRD's exact compare is a false-negative machine; equal-to-nine-digits ≠ wrong |
| `order_insensitive` (gated) | order-blind always | **stricter** | when the gold orders, a broken `ORDER BY` is a real bug BIRD can't see |
| multiset (keep dups) | `set()` collapses | **stricter** | `COUNT` vs `COUNT DISTINCT` is a real bug BIRD can't see |

Two of our three divergences make us *stricter* than BIRD — we reject answers it
accepts, because its `set()` is blind to order and to duplicates. One makes us *more
lenient* — we forgive floating-point noise it penalizes. None of this is an accident
or a bug; it's a documented refinement, written up in
[`docs/eval/comparator-rule-set.md`](../eval/comparator-rule-set.md) as the
"here's how I know my evaluator is correct" reference.

But "documented" isn't enough — the project's standard is *proven by the fixture,
not asserted.* So the final slice adds a `set` rule (BIRD's primitive: collapse to a
set, in one step) and an opt-in `BIRD_RULES` tuple that reproduces BIRD's verdict
exactly:

```python
BIRD_RULES = ("column_position", "set", "exact")
```

…and then pins every divergence as a **pair** of fixture triples on identical data —
one scored BIRD's way, one scored ours:

```jsonc
// fixtures/golden_compare/bird_alignment.json
{ "id": "divergence-multiset__bird-collapses-duplicates",
  "gold_result":      {"rows": [["paid"], ["paid"], ["failed"]]},
  "candidate_result": {"rows": [["paid"], ["failed"]]},
  "rules": ["column_position", "set", "exact"],
  "expected_verdict": "correct" }      // BIRD: the lost duplicate is invisible

// same data, our default rules → "incorrect": we catch the dropped row
```

The gap between those two verdicts is not a discrepancy to hide. It's a *quantity*:
run any result set through `DEFAULT_RULES` and `BIRD_RULES` and the difference is
exactly the set of bugs BIRD's `set()` comparison masks. Being able to report both
numbers — and explain the delta — is worth more than a single number that hides
which of the two it is.

---

## Proven, not asserted

Step 2's definition of done is one sentence: **the comparator passes its entire
golden fixture.** At the close of the step that's 62 green tests in the
comparator's own suite — the whole fixture plus rule-level unit checks, inside a
fully-green 159-test repo — every subtle decision pinned by a named case you can
read:

```
$ uv run pytest tests/test_compare.py -v
...
test_golden_compare[bird_alignment:divergence-order__bird-ignores-order-by] PASSED
test_golden_compare[bird_alignment:divergence-order__ours-rejects-reorder-when-gold-orders] PASSED
test_golden_compare[value_shape:multiset-count-vs-count-distinct] PASSED
test_golden_compare[order_sensitivity:order-significant-wrong-order-incorrect] PASSED
...
```

The fixture isn't test scaffolding you throw away. It's the artifact you point at
when someone asks "how do you know your scorer is right?" — and the answer is a file
of cases, not a paragraph of confidence.

> **An honesty note on process.** The value-and-shape slice was, briefly, a lie of
> a different kind: its PR was merged — into the wrong base branch. GitHub cheerfully
> reported it "merged" and the issue "completed," and yet the code never reached
> `main`. The work *looked* done; it wasn't. The same instinct that drives the
> fixture caught it: don't trust the green checkmark, check the artifact. The rules
> were re-landed, reconciled onto the real `main`, and the episode bought a standing
> rule — verify the base branch, every time. Measurement discipline isn't only for
> the model.

---

## What we refused to build

Scope discipline, again, is a feature. Step 2 did **not** build:

- **An LLM-as-judge.** The comparator is deterministic — no model calls, no regex
  for SQL semantics, sqlglot ASTs only. An objective result-set check is the ground
  truth; a judge is explicitly not the core scorer.
- **A `set`-by-default scorer.** We could have matched BIRD exactly and saved
  ourselves three divergences to defend. We chose the stricter, more honest default
  and made BIRD-parity an opt-in instead.
- **A `RESULTS.md` entry.** Still no benchmark number — that discipline starts at
  Step 3, when the harness scores a frozen, seeded slice. A proven scorer with
  nothing yet scored is exactly the right amount of nothing to report.

---

## What's next

- **Step 3** — the minimal harness points the proven comparator at a frozen, seeded
  BIRD slice and the *first real numbers* land in `RESULTS.md`: pass@1 on a
  small-schema slice, every number traceable to model, slice, prompt version, and
  commit.

Step 1 proved the machine runs. Step 2 built the instrument that says how *well* it
runs, and proved the instrument before trusting it. Now we get to point it at
something and read the dial — which, from the start, was the product.
