"""Stage: execute — SQLAlchemy execution of candidate SQL.

Multi-engine by design (SQLite for BIRD, Postgres for the demo, BigQuery later);
Step 1 (issue 4) targets the payments Postgres db. The stage takes an
``Engine`` so the caller owns connection/identity (single-db per run) and so the
executor stays decoupled from any dataset package.

Observability contract (CLAUDE.md §5.3): the *raw* result set may carry PII, so
only the row count and column names — never the rows — are attached to the obs
span. The raw result lives on the run state for upstream scoring; redaction runs
later (Step 8) before anything is presented or logged.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState

DEFAULT_DB_URL = "postgresql://payments:payments@localhost:5432/payments"


def get_engine(db_url: str | None = None) -> Engine:
    """SQLAlchemy engine for the target db (``PAYMENTS_DB_URL`` or the default)."""
    url = db_url or os.environ.get("PAYMENTS_DB_URL", DEFAULT_DB_URL)
    return create_engine(url, future=True)


def execute(state: RunState, engine: Engine) -> RunState:
    """Run ``state.candidate_sql`` against ``engine``; store rows/columns or error.

    On success, populates ``result_columns`` and ``result_rows``. On a database
    error, captures the message on ``state.error`` and leaves the result empty —
    the harness classifies the terminal state, not this stage. Returns ``state``.
    """
    with stage_span("execute", db_id=state.db_id) as extra:
        if not state.candidate_sql:
            state.error = "no candidate SQL to execute"
            extra["error"] = "missing_sql"
            return state

        try:
            with engine.connect() as conn:
                # exec_driver_sql, not execute(text(...)): candidate SQL is always
                # a fully literal statement with no external bind parameters, and
                # SQLAlchemy's ``:name`` bind-parameter scan can misfire on a plain
                # string literal that happens to contain a colon (e.g. a time
                # value like '1:23.456') — exec_driver_sql sends the SQL to the
                # DBAPI unparsed, sidestepping that scan (and the false
                # execution_error it would otherwise produce) entirely.
                result = conn.exec_driver_sql(state.candidate_sql)
                state.result_columns = list(result.keys())
                state.result_rows = [tuple(row) for row in result.fetchall()]
            # Only the shape is logged — never the rows (they may carry PII).
            extra["row_count"] = len(state.result_rows)
            extra["column_count"] = len(state.result_columns)
        except SQLAlchemyError as exc:
            state.error = str(exc)
            # Log the exception class only; the message can echo the query text.
            extra["error"] = type(exc).__name__

    return state
