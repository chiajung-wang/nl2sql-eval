"""Stage wiring: the hand-rolled state machine.

Step 1 (issue 4) wired a linear ``generate → guard → execute → return``. Step 5
(issue #42) turns that single shot into an **agent**: a capped retry loop that,
on an execution error, feeds the failure back through ``correct`` into a fresh
``generate``. LangGraph swaps in at Step 7 only after the logic is proven by the
eval harness; loop-aware retrieve (re-retrieve on not-found) is Step 6.

The pipeline is import-shared: ``eval/harness.py`` and ``apps/demo/`` both call
``run_pipeline`` with the *same* logic — never a fork. Schema text and the
``Engine`` are inputs so this module depends on neither the dataset packages nor
the eval layer.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from nl2sql.obs import stage_span
from nl2sql.pipeline.correct import correct
from nl2sql.pipeline.execute import execute
from nl2sql.pipeline.generate import DEFAULT_DIALECT, DEFAULT_MODEL, generate
from nl2sql.pipeline.guard import guard
from nl2sql.pipeline.state import RunState

# Single-shot by default (the pass@1 mode): no correction unless a caller opts
# into a budget. The harness raises this for pass@k; the cap is the explicit,
# configurable cost/latency lever the plan calls out.
DEFAULT_MAX_ATTEMPTS = 1


def run_pipeline(
    question: str,
    *,
    schema: str,
    engine: Engine,
    db_id: str = "payments",
    dialect: str = DEFAULT_DIALECT,
    evidence: str = "",
    model: str = DEFAULT_MODEL,
    client: Any | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> RunState:
    """Run one question through the capped ``generate → guard → execute`` loop.

    Each cycle: ``generate`` (feeding back any prior failure via
    ``state.correction``), then the deterministic guard gate *before* execution —
    a rejected candidate sets ``state.guard_rejected``, never reaches the
    database, and ends the run (the guard-feedback loop is out of Step-5 scope).
    On a clean ``execute`` the run returns immediately. On an execution error the
    ``correct`` stage stages the failure as feedback and the loop regenerates,
    until the candidate succeeds or the ``max_attempts`` budget is spent.

    ``max_attempts=1`` (default) is the single-shot pass@1 mode — no correction.
    Returns the populated ``RunState``; scoring and terminal-state classification
    (a budget-exhausted error → ``RETRY_EXHAUSTED``, a single-shot error →
    ``EXECUTION_ERROR_FINAL``) are the harness's job, keyed off ``attempts``.
    ``dialect``/``evidence`` thread into generate, and the same ``dialect``
    parses the candidate in guard (SQLite on the BIRD path; PostgreSQL for the
    payments demo).
    """
    budget = max(1, max_attempts)
    with stage_span("pipeline", db_id=db_id, max_attempts=budget):
        state = RunState(question=question, db_id=db_id, max_attempts=budget)
        while True:
            state.attempts += 1
            generate(
                state,
                schema,
                dialect=dialect,
                evidence=evidence,
                model=model,
                client=client,
            )
            guard(state, dialect=dialect)
            if state.guard_rejected:
                return state
            execute(state, engine)
            if state.error is None or state.attempts >= budget:
                return state
            correct(state)


def _smoke() -> None:
    """Dev smoke entry: feed one payments question end-to-end and print the result.

    Reads the committed payments DDL by path (a data file, not an import — the
    pipeline does not depend on ``eval/``) and uses ``PAYMENTS_DB_URL``. Requires
    a live, seeded Postgres and ``ANTHROPIC_API_KEY``:

        docker compose up -d
        uv run python -m eval.datasets.payments.load
        uv run python -m nl2sql.pipeline.graph "How many users are from the US?"
    """
    import logging
    import sys
    from pathlib import Path

    from nl2sql.pipeline.execute import get_engine

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    question = sys.argv[1] if len(sys.argv) > 1 else "How many users are there?"
    repo_root = Path(__file__).resolve().parents[3]
    schema = (repo_root / "eval/datasets/payments/schema.sql").read_text()

    state = run_pipeline(question, schema=schema, engine=get_engine())

    print(f"\nQ: {state.question}")
    print(f"SQL: {state.candidate_sql}")
    if state.error:
        print(f"ERROR: {state.error}")
    else:
        print(f"columns: {state.result_columns}")
        print(f"rows: {state.result_rows}")


if __name__ == "__main__":
    _smoke()
