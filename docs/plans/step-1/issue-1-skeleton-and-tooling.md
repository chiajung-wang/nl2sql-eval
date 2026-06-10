# Issue 1 — Skeleton & tooling

**Type:** AFK
**Phase:** Step 1 (Foundation) — *Prove the machine runs end-to-end*

## Parent

`docs/plans/step-1/plan-step-1.md`

## What to build

Stand up the repository skeleton so every later slice has a home and imports resolve. This is the `uv`-managed project plus the full PRD §8 module tree as stubs, the shared run-state, and the thin observability seam — no behavior yet.

Includes:
- `uv` project (`pyproject.toml`), Python 3.11+ floor.
- The full PRD §8 directory tree with **empty stub modules** under `src/nl2sql/` (`pipeline/{graph,state,retrieve,generate,guard,execute,correct,redact}.py`, `schema_index/`, `llm/`, `obs/`), plus `eval/`, `fixtures/`, `prompts/`, `apps/demo/`, `tests/` placeholders so imports resolve.
- `state.py`: the run-state dataclass **and** the *complete* terminal-state enum (`success`, `wrong_answer`, `retry_exhausted`, `execution_error_final`, `guardrail_rejected`, `retrieval_empty`) — define the whole enum now even though only `success`/`execution_error_final` are reachable in Step 1, so later steps never reshape `state.py`. The terminal-state **classifier does not live here** — enum only.
- A thin obs seam in `obs/`: a structured-logging hook callable at each stage. No-op / plain logging, **not** wired to Langfuse.
- Lint/format config (ruff assumed) wired so `uv run ruff check .` passes.

`sqlglot` may be added as a dependency (it's stable) but is **not used** in Step 1.

## Acceptance criteria

- [ ] `uv sync` succeeds against a committed `pyproject.toml`.
- [ ] Every module in the PRD §8 tree exists and `uv run python -c "import nl2sql..."` resolves all of them without error.
- [ ] `state.py` defines the run-state dataclass and the full 6-value terminal-state enum; no classifier logic present.
- [ ] An obs logging seam exists and is callable per stage (no-op/structured log; not Langfuse).
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean.

## Blocked by

None — can start immediately.

---

**Tracked on GitHub:** [#6](https://github.com/chiajung-wang/nl2sql-eval/issues/6) — _closed (completed)_
