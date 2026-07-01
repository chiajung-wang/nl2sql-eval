# CLAUDE.md

Guidance for AI agents working in this repository. These rules are derived from `docs/prd.md`; when in doubt, defer to the PRD. This file holds the **behavioral rules** an agent must not violate. For reference material (setup, commands, full directory tree, config keys), see `README.md` — sections are cited inline below.

## 1. Framing (read first)

`nl2sql-eval` is a Guardrailed Agentic NL-to-SQL system presented as a **case study in rigorously evaluating and operating an LLM system**. The NL-to-SQL agent is the *workload*; the eval harness, observability, and prompt-CI/CD wrapper is the *product*.

**The measurement apparatus is the centerpiece. Build the eval before the features** (PRD §9). `eval/` is a peer of `src/`, never subordinate.

> Project overview, features, and tech-stack rationale: see `README.md` → *Features*, *Configuration & Data Sources*. Inferred-vs-PRD defaults (tooling, lint, Python floor, env-var names): see `README.md` → *Assumptions*. Verify those against the real `pyproject.toml` before relying on them.

## 2. Key tech choices (non-negotiable)

- **sqlglot** for all SQL parsing/validation — AST-based. **Never `sqlparse`** (tokenize-only).
- **SQLAlchemy** executor; **LiteLLM** for providers (Step 7+); **Langfuse** for observability.
- Default to the latest capable Claude models (Opus 4.x / Sonnet 4.x) when invoking Claude.

> Full stack table and prerequisites: `README.md` → *Prerequisites*, *Features*.

## 3. Architecture — module boundaries (rules, not the tree)

The pipeline is an instrumented state machine wrapped by a harness that treats it as `question → result`. **Full directory tree: `README.md` → *Project Structure*.** The rules that the tree must always satisfy:

- **One pipeline stage per module** under `src/nl2sql/pipeline/`. Do not collapse stages into one file. Stages: `retrieve → generate → guard → soundness → execute → correct → redact`. (`soundness`, Step 12 #139, is a post-guard deterministic bad-construction check whose hits are **correction signals**, not terminal rejections — a flag with budget left feeds back; with the budget spent the candidate still executes. `link.py`, #138, is the task-alignment alternative to `retrieve`, selected by config.)
- **The pipeline is import-shared.** Both `eval/harness.py` and `apps/demo/` import the *same* pipeline. Never fork or duplicate pipeline logic for the demo — no drift between what is demoed and what is measured.
- **Two pipeline exits (critical):**
  - **Raw verified result** — scored by the harness against gold, **upstream of redaction**.
  - **Presented result** — post-redaction; the *only* thing shown to users or written to traces/logs.
- **Terminal states** (every run buckets into exactly one): `success`, `wrong_answer`, `retry_exhausted`, `execution_error_final`, `guardrail_rejected`, `retrieval_empty`. The **enum lives in `state.py`**; the **classifier lives in the harness**, never in `state.py`.

## 4. Code conventions

- **Python 3.11+**, `uv`-managed. Add deps via `uv add`, never hand-edit lockfiles.
- File organization mirrors §3. snake_case modules/functions, PascalCase classes.
- **Prompts are externalized** as version-controlled Jinja-style templates in `prompts/`. Never inline prompt strings in Python — CI diffs `prompts/`.
- **Guardrails and the comparator are deterministic.** No LLM calls, no regex for SQL semantics — sqlglot ASTs only.

## 5. Domain rules (correctness invariants)

1. **Execution accuracy via canonicalized result-set comparison, never SQL string-match.** Two different queries can be equally correct.
2. **Scoring happens upstream of redaction.** The harness scores the *raw verified result*; redaction runs afterward and must never corrupt scoring.
3. **Raw PII never reaches logs or traces.** Only the *presented (redacted) result* is logged. Redaction is column-aware, deterministic, schema-driven.
4. **Guardrails are deterministic sqlglot AST checks, pre-execution:** read-only enforcement (block writes/DDL), dangerous-op blocking, cost/complexity check (**heuristic-first**; `EXPLAIN` only where supported — Postgres enhancement, not the BIRD/SQLite path), and per-db table-scope check. On fail: reject **or** feed back as a correction signal.
5. **Self-correction is capped.** Errors and not-found feedback re-trigger regeneration/re-retrieval within a **capped retry budget**.
6. **Report twin metrics: `pass@1` AND `pass@k`.** The gap quantifies what self-correction is worth.
7. **Report retrieval lift:** naive-baseline vs schema-RAG accuracy, plus **retrieval recall** vs the gold query's actual tables.
8. **Single-db per run.** The db identity is an *input* (BIRD tags each question). Cross-db **routing is out of scope**.
9. **Repeatability:** eval slices are **frozen, seeded, stratified**; prompts version-controlled; the frozen BIRD slice ID list lives in `eval/datasets/bird/`.
10. **The comparator must be proven** via the golden fixture `(gold, candidate, expected_verdict)` triples in `fixtures/golden_compare/`.
11. **Guardrails must be measured** against `fixtures/redteam_guard/` (reported catch rate).

## 6. The running results log (Step 3 onward)

**A step is not done until its number is appended to `RESULTS.md`** with the exact config: **model, slice ID, prompt version, date, the number, and the commit**. Every reported number must be traceable to its config and commit. Capture especially the **pass@1→pass@k gap** (Step 5) and the **naive-baseline→retrieval lift** (Step 6).

> **Per-issue delivery loop:** for each `docs/plans/step-N/issue-*.md`, follow the workflow in `docs/per-issue-workflow.md` (worktree → implement+verify → PR to `main` → `/review` → fix → issue summary HTML → next issue → Step-N blog post). Don't skip the review or the summary.

## 7. Anti-patterns — never do these

- Compare SQL by **string-match** (use result-set comparison).
- Use **`sqlparse`** for validation (use `sqlglot`).
- Use **regex or an LLM judge** for guardrails or as the primary scorer.
- Let **raw PII** reach logs, traces, or the presented result.
- Put the **terminal-state classifier in `state.py`**.
- **Inline prompts** in Python (keep them in `prompts/`).
- Report an eval number **without** a corresponding `RESULTS.md` entry and commit.
- Build an explicit **non-goal**: cross-db routing, open-ended generation eval, LLM-as-judge-as-primary-scorer (PRD §11).
- Let **BigQuery** integration block the README/blog — it is quarantined optional reach.
- Add **Claude / Claude Code as co-author or author** on commits or PRs. Never include `Co-Authored-By: Claude` trailers or "Generated with Claude Code" lines in commit messages or PR bodies.

## 8. Testing

Tests concentrate on the deterministic cores — `eval/compare.py`, `src/nl2sql/pipeline/guard.py`, and `src/nl2sql/pipeline/soundness.py`. The comparator must pass its **entire** golden fixture; guardrails must be unit-green and measured against the red-team fixture; the soundness checks are measured against `fixtures/soundness/` (reported catch rate **and** false-positive rate). Add a fixture case for every new comparison edge case, dangerous-query pattern, or bad-construction pattern. **Commands and details: `README.md` → *Testing*.**

## 9. Definition of done (the unique checks)

- Module boundaries and import-sharing (§3) intact; no pipeline logic duplicated for the demo.
- Comparator (if touched) passes the **entire** golden fixture; guardrails (if touched) pass unit tests + red-team fixture.
- Scoring upstream of redaction; raw PII never reaches logs/traces/presented output.
- `pass@1` and `pass@k` (and retrieval recall where relevant) reported — not just overall accuracy.
- Any eval number appended to `RESULTS.md` (model, slice ID, prompt version, date, number, commit).
- Prompts changed live in `prompts/` as templates.
- `uv run pytest` passes; lint/format clean.
- No work on an explicit non-goal.
- `CLAUDE.md` **and** `README.md` updated together if commands/structure/stack changed.
