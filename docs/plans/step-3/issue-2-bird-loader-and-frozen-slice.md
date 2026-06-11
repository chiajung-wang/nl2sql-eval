# Issue 2 — BIRD loader + frozen small-schema slice

**Type:** AFK
**Phase:** Step 3 (Foundation) — *Produce the first trustworthy measured claim*

## Parent

`docs/plans/step-3/plan-step-3.md`

## What to build

The BIRD dataset adapter and the frozen evaluation slice that anchors every future number. This is the slice that gives the harness a real benchmark to run against, deliberately scoped to keep the first number trustworthy.

Includes:
- **`eval/datasets/bird/`** — a loader/adapter for BIRD: SQLite, **file-per-db**. Each question carries its **tagged** db identity and runs against that db only (single-db per run; cross-db **routing is out of scope**, CLAUDE.md §5.8). Loads the question + gold SQL and connects to the correct db file for execution.
- **A frozen, seeded, stratified slice** drawn from **smaller-schema** BIRD dbs first, checked into the repo as an **explicit ID list** under `eval/datasets/bird/` (CLAUDE.md §5.9). Rationale: with no retrieval yet, the whole schema is dumped into the prompt; large-schema dbs would overflow context and tank accuracy for reasons unrelated to generation quality. Small-schema-first keeps the baseline honest.
- Demoable end-to-end: load the slice → run one BIRD question against its tagged db → score it via `compare.py`.

Scope guard: no large-schema dbs in the slice yet (contaminates the baseline with context-overflow effects). Requires BIRD data downloaded locally (`BIRD_DATA_DIR`); the loader/selection logic should be unit-testable without the full download.

## Acceptance criteria

- [ ] `eval/datasets/bird/` loads BIRD questions and connects each to its tagged SQLite db (file-per-db; no routing).
- [ ] A frozen slice is checked in as an explicit, seeded ID list under `eval/datasets/bird/`.
- [ ] The slice is drawn from smaller-schema dbs only; selection is seeded and reproducible.
- [ ] A single BIRD question can be loaded, executed against its db, and scored end-to-end via `compare.py`.
- [ ] `uv run pytest` passes (loader/selection logic unit-tested without requiring the full BIRD download); lint/format clean.

## Blocked by

None — can start immediately (parallel with Issue 1).

---

## Tracking

**GitHub:** [#27](https://github.com/chiajung-wang/nl2sql-eval/issues/27) · label `agent-ready`, `step-3`

**Blocked by (GitHub):** None — can start immediately

**Step 3 set:** [#26](https://github.com/chiajung-wang/nl2sql-eval/issues/26) · [#27](https://github.com/chiajung-wang/nl2sql-eval/issues/27) · [#28](https://github.com/chiajung-wang/nl2sql-eval/issues/28)
