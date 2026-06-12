# Issue 4 — BigQuery connection via sqlglot transpilation (optional reach)

**Type:** AFK
**Phase:** Step 10 (Amplification) — *Polish & reach* · **Optional reach — must not block the non-negotiables**

## Parent

`docs/plans/step-10/plan-step-10.md`

## What to build

The cloud-warehouse checkbox: a **BigQuery connection** via sqlglot transpilation. This is **optional reach** — real integration risk (auth, dialect quirks, cost surprises). If it slips, ship without it; an unreadable repo is fatal, a missing cloud checkbox is not.

- Add a BigQuery executor path, transpiling the verified SQL via sqlglot to the BigQuery dialect.
- Keep it behind an isolated/optional configuration so it never blocks the BIRD/SQLite path or the README/blog.
- Quarantine the integration so auth/cost/dialect issues can't derail the legibility deliverables.

## Acceptance criteria

- [ ] A BigQuery executor path exists, transpiling via sqlglot to the BigQuery dialect
- [ ] BigQuery is optional/quarantined — it never blocks the SQLite/BIRD path or the README/blog
- [ ] If integration risk materializes, the project still ships without it (documented as optional)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- Steps 1–9 ([#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59)). Independent of [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60)/[#61](https://github.com/chiajung-wang/nl2sql-eval/issues/61)/[#62](https://github.com/chiajung-wang/nl2sql-eval/issues/62) — and explicitly must not block them.

---

## Tracking

**GitHub:** [#63](https://github.com/chiajung-wang/nl2sql-eval/issues/63) · label `agent-ready`, `step-10`

**PR:** _pending_

**Blocked by (GitHub):** [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59) (Steps 1–9 complete) — but must not block #60/#61/#62

**Step 10 set:** [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60) · [#61](https://github.com/chiajung-wang/nl2sql-eval/issues/61) · [#62](https://github.com/chiajung-wang/nl2sql-eval/issues/62) · [#63](https://github.com/chiajung-wang/nl2sql-eval/issues/63) (#63 optional reach)
