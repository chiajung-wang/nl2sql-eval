# Issue 1 — Baseline error-analysis diagnostic (taxonomy + scorer-vs-model split)

**Type:** AFK
**Phase:** Step 11 (Optimization) — *Closing the accuracy gap* · **DONE**

## Parent

`docs/plans/step-11/plan-step-11.md`

## What to build

Turn "pass@1 0.420, 29 wrong" into an **actionable failure taxonomy** so the improvement work is targeted, not guessed.

- Run the frozen Step-3 slice once (single-shot, naive dump — the baseline config). For every failure, emit the **gold vs candidate SQL**, the comparator reason, and a **deterministic sqlglot-AST root-cause tag** (table / join / aggregate / group-by / distinct / where / limit / projection mismatch), counted into a taxonomy.
- **Re-score each failure under BIRD set-semantics** (`BIRD_RULES`) to separate **scorer-strictness false-negatives** from **genuine model errors** — only the latter are worth fixing.
- Tagging is sqlglot-AST-only (no regex for SQL semantics, no LLM); no result rows emitted.

## Acceptance criteria

- [x] Per-failure gold-vs-candidate dump with AST root-cause tags, counted into a taxonomy
- [x] Scorer-vs-genuine split via `BIRD_RULES` re-scoring (pass@1 strict vs BIRD set-semantics)
- [x] Difficulty/db breakdowns; committed artifact under `docs/plans/step-3/`
- [x] `uv run pytest` green (offline tagger tests); lint clean

## Outcome

**Done** — PR #110. Findings (`docs/plans/step-3/baseline-failures.md`): pass@1 **0.420 strict / 0.460 BIRD set-semantics** (only 2 scorer artifacts), **27/29 genuine**, dominant buckets **table_mismatch (9) + join_mismatch (7)**, moderate-difficulty worst (**0.263**). Reproduce: `uv run python -m eval.diagnose_bird`.

---

## Tracking

**GitHub:** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) · label `agent-ready`, `step-11`

**PR:** [#110](https://github.com/chiajung-wang/nl2sql-eval/pull/110) (merged)

**Step 11 set:** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) · [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112) · [#113](https://github.com/chiajung-wang/nl2sql-eval/issues/113)
