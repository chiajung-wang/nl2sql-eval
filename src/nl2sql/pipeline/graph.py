"""Stage wiring: the hand-rolled state machine.

Step 1 (issue 4) wires a linear ``generate → execute → return`` — no loop, no
conditional edges. Guard, correct, and loop-aware retrieve arrive in later
steps; LangGraph swaps in at Step 7 only after the logic is proven by the eval
harness.

The pipeline is import-shared: ``eval/harness.py`` and ``apps/demo/`` both call
``run_pipeline`` with the *same* logic — never a fork. Schema text and the
``Engine`` are inputs so this module depends on neither the dataset packages nor
the eval layer.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from nl2sql.obs import stage_span
from nl2sql.pipeline.execute import execute
from nl2sql.pipeline.generate import DEFAULT_MODEL, generate
from nl2sql.pipeline.state import RunState


def run_pipeline(
    question: str,
    *,
    schema: str,
    engine: Engine,
    db_id: str = "payments",
    model: str = DEFAULT_MODEL,
    client: Any | None = None,
) -> RunState:
    """Run one question through the linear ``generate → execute → return`` path.

    Returns the populated ``RunState`` (with ``candidate_sql`` and either the
    result set or an ``error``). Scoring and terminal-state classification are
    the harness's job, not the pipeline's.
    """
    with stage_span("pipeline", db_id=db_id):
        state = RunState(question=question, db_id=db_id)
        generate(state, schema, model=model, client=client)
        execute(state, engine)
        return state


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
