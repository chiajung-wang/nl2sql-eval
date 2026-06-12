"""Stage wiring: the hand-rolled state machine.

Step 1 (issue 4) wired a linear ``generate → guard → execute → return``. Step 5
(issue #42) turns that single shot into an **agent**: a capped retry loop that,
on an execution error, feeds the failure back through ``correct`` into a fresh
``generate``. Step 6 (issue #46) makes that loop **retrieval-aware**: a not-found
execution error re-retrieves a widened schema (not only regenerates), inside the
same capped budget. LangGraph swaps in at Step 7 only after the logic is proven by
the eval harness.

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
from nl2sql.pipeline.retrieve import is_not_found_error, retrieve
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import DEFAULT_MAX_TABLES, SchemaIndex

# Single-shot by default (the pass@1 mode): no correction unless a caller opts
# into a budget. The harness raises this for pass@k; the cap is the explicit,
# configurable cost/latency lever the plan calls out.
DEFAULT_MAX_ATTEMPTS = 1


def run_pipeline(
    question: str,
    *,
    schema: str | None = None,
    schema_index: SchemaIndex | None = None,
    engine: Engine,
    db_id: str = "payments",
    dialect: str = DEFAULT_DIALECT,
    evidence: str = "",
    model: str = DEFAULT_MODEL,
    client: Any | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_tables: int = DEFAULT_MAX_TABLES,
) -> RunState:
    """Run one question through the capped ``generate → guard → execute`` loop.

    The generator's schema comes from one of two mutually exclusive sources. Pass
    ``schema_index`` for **schema-RAG** (Step 6): the ``retrieve`` stage selects
    the tables relevant to *this* question and ``generate`` sees only those.
    Pass ``schema`` for the Step-3 **naive full-schema dump** (the retrieval-lift
    baseline; still how the payments demo runs). Exactly one is required.

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
    if (schema is None) == (schema_index is None):
        raise ValueError("run_pipeline needs exactly one of schema= or schema_index=")
    budget = max(1, max_attempts)
    with stage_span("pipeline", db_id=db_id, max_attempts=budget):
        state = RunState(question=question, db_id=db_id, max_attempts=budget)
        # Initial retrieval (schema-RAG) or the naive full dump on the baseline path.
        active_schema = (
            retrieve(state, schema_index, max_tables=max_tables)
            if schema_index is not None
            else schema
        )
        re_retrievals = 0
        while True:
            state.attempts += 1
            generate(
                state,
                active_schema,
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
            # Loop-aware re-trigger (#46): a not-found error means the schema the
            # generator saw was too narrow — route it back into *retrieval* and
            # widen, not only into regeneration. Capture the error before
            # ``correct`` clears it; the re-retrieve stays inside the same budget.
            re_retrieve = schema_index is not None and is_not_found_error(state.error)
            error_hint = state.error or ""
            correct(state)
            if re_retrieve:
                re_retrievals += 1
                # Widen coverage each time: max_tables → 2× → 4× …, reaching the
                # full schema at the widest. Bounded by the retry budget above.
                floor = max_tables * 2**re_retrievals
                active_schema = retrieve(
                    state,
                    schema_index,
                    max_tables=max_tables,
                    floor=floor,
                    hint=error_hint,
                )


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
