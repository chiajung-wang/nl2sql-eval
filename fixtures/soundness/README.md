# `soundness/` — the bad-construction (soundness) fixture

A **named deliverable** (Step 12, #139; source: Shkapenyuk et al.,
arXiv:2505.19988v2 §4). The deterministic soundness checks
(`src/nl2sql/pipeline/soundness.py`) are only as trustworthy as the fixture that
proves them, so every check is measured against a labeled corpus of positive
(should-flag) and near-miss negative (should-not-flag) queries here — the
**catch rate** and **false-positive rate** are reported in `RESULTS.md`.

## Soundness vs. the guard

These are the *same AST-check shape* as `fixtures/redteam_guard/`, but a
**different contract**. A guard hit is a terminal `GUARDRAIL_REJECTED` (a safety
gate). A soundness hit is a **correction signal**: with retry budget left the
graph feeds the reason back to `generate`; with the budget spent the candidate
executes anyway. A soundness heuristic must never *lose* a run, so a false
positive costs at most a wasted retry — which is why the **false-positive rate**
(measured over the `pass` cases) is a first-class number here, not just catch rate.

## Format

Each `*.json` file holds a `_meta` block and a `cases` list. Every case is a
`(candidate SQL, expected verdict)` pair:

| field | meaning |
| --- | --- |
| `id` | stable case id (used in the test parametrization) |
| `description` | what the case proves |
| `sql` | the candidate SQL fed to `check_soundness_sql` |
| `dialect` | optional; the sqlglot parse dialect (default `SQLite`) |
| `expected_verdict` | `flag` (soundness hit) or `pass` (clean) |
| `expected_rule` | on a `flag`, the check that should fire |

`tests/test_soundness.py` replays every case through `check_soundness_sql` and
asserts the verdict — adding a case is exercised automatically. The `flag` cases
form the **catch-rate set**; the `pass` cases form the **false-positive set** (a
flag on a `pass` case is a false positive).

## Coverage

- `null_ordering.json` — `min(f)` / `ORDER BY f ASC LIMIT` over an unguarded
  column (NULL sorts first → NULL-driven wrong answer), with near-miss negatives:
  an `IS NOT NULL` / comparison guard, `MAX`/`DESC` (NULLs sort last), a full
  ordered list, and a scalar-`MIN` building-block subquery.
- `minmax_subquery.json` — selecting a row by `= (SELECT MIN/MAX(x) …)` where
  `ORDER BY x LIMIT 1` is idiomatic, with near-miss negatives: a *correlated*
  subquery (needs the subquery form), a non-equality comparison, and a plain
  aggregate.
- `field_catenation.json` — a projection that fuses two or more distinct fields
  via `||` / `CONCAT`, with near-miss negatives: a column concatenated with a
  string literal, and separate columns.

**Scope.** The checks judge the **outermost query** — the result the user
receives — not nested building-block subqueries (a scalar `MIN(x)` subquery is a
common, correct idiom). All three checks are correction signals, never hard
rejects.
