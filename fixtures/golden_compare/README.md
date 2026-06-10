# `golden_compare/` — the comparator's proof fixture

`(gold_result, candidate_result, expected_verdict)` triples that prove
`eval/compare.py` is trustworthy. **DELIVERABLE** — this is the artifact you
point at to answer "how do I know my evaluator is correct?", not throwaway test
data. A comparator bug silently invalidates every reported number, so the
comparator must pass its **entire** golden fixture (CLAUDE.md §8, §10).

## Layout

One JSON file per rule group. Every `*.json` here is loaded and exercised by
`tests/test_compare.py` — **adding a case (or a new file) is picked up
automatically**, no test edits required.

- `baseline.json` — Issue 11: the trivial rules. Exact value equality, a plainly
  different result, and the empty result handled as its own correct-able case.

Later Step-2 issues add their own files for the subtle rules (order-sensitivity
gated on `ORDER BY`, NULL/float/column canonicalization, multiset semantics,
BIRD-evaluator alignment).

## Case format

```json
{
  "cases": [
    {
      "id": "identical-rows",
      "description": "why this case exists",
      "gold_sql": "SELECT ...",
      "gold_result": {"columns": ["n"], "rows": [[3]]},
      "candidate_result": {"columns": ["n"], "rows": [[3]]},
      "expected_verdict": "correct"
    }
  ]
}
```

- `expected_verdict` is `"correct"` or `"incorrect"`.
- Optional `"rules"` (a list of canonicalization-rule names) overrides
  `eval.compare.DEFAULT_RULES` for that one case.
- Comparison is on result-set **values**, never the SQL string and (in this
  slice) not column labels — a correct value under a different alias is still
  correct (CLAUDE.md domain rule 1).
