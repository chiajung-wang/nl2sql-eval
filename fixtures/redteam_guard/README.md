# `redteam_guard/` — the guardrail red-team fixture

A **named deliverable** (PRD / plan-step-4). The deterministic guard gate
(`src/nl2sql/pipeline/guard.py`) is only as trustworthy as the fixture that
proves it works, so every check is measured against a labeled corpus of
adversarial inputs here.

## Format

Each `*.json` file holds a `_meta` block and a `cases` list. Every case is a
`(candidate SQL, expected verdict)` pair:

| field | meaning |
| --- | --- |
| `id` | stable case id (used in the test parametrization) |
| `description` | what the case proves |
| `sql` | the candidate SQL fed to `guard_sql` |
| `dialect` | optional; the sqlglot parse dialect (default `sqlite`) |
| `expected_verdict` | `allow` or `reject` |
| `expected_rule` | on a reject, the rule that should fire (e.g. `read_only`) |

`tests/test_guard.py` loads every case and asserts `guard_sql` reproduces the
verdict — adding a case is exercised automatically. Cases with
`expected_verdict: "reject"` form the **red-team set** the catch rate is computed
over (reported in `RESULTS.md` at the close of Step 4).

## Coverage (filled in across Step 4)

- `read_only.json` — write/DDL rejection + benign read-only allows (Issue 1).
- `dangerous_op.json` — stacked statements, `ATTACH`/`DETACH`, `PRAGMA`, and
  unmodeled commands (Issue 2).
- `cost.json` — cartesian products, join explosion, unbounded `SELECT *` scans
  (heuristic-first, calibrated against the BIRD gold) (Issue 3).
- `prompt_injection.json` — natural-language attacks that try to *induce*
  dangerous SQL, each paired with the induced payload + expected verdict; the
  deterministic gate is the backstop, proven on the generate → guard path (Issue 4).

**Out of scope here:** table-scope enforcement needs a per-db allowed-tables list
(schema metadata formalized in Step 6) and is deliberately not exercised yet.
