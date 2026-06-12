"""Stage: retrieve — schema-RAG over table/column metadata + sample values.

Replaces the Step-3 naive full-schema dump: score the db's tables against *this*
question (deterministic lexical overlap, see ``nl2sql.schema_index``) and hand
``generate`` only the relevant tables' definitions instead of every table. The
selected table names are recorded on the state so the harness can measure
**retrieval recall** against the gold query's tables (a later Step-6 slice).

Single-shot here; the loop-aware re-trigger (re-retrieve on a not-found error,
feeding the error back as signal) is the next slice. The pipeline is
import-shared — the harness and the demo build the index and call this the same
way, never a fork.
"""

from __future__ import annotations

from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import DEFAULT_MAX_TABLES, SchemaIndex


def retrieve(
    state: RunState,
    index: SchemaIndex,
    *,
    max_tables: int = DEFAULT_MAX_TABLES,
) -> str:
    """Select the relevant tables for ``state.question`` and render their schema.

    Records the chosen table names on ``state.retrieved_tables`` (for the recall
    metric) and returns the focused schema string the generator consumes. Only
    table *names* and counts reach the span — schema metadata, never result rows.
    """
    with stage_span("retrieve", db_id=state.db_id) as extra:
        tables = index.relevant_tables(state.question, max_tables=max_tables)
        state.retrieved_tables = tables
        extra["retrieved_tables"] = tables
        extra["n_tables"] = len(tables)
        return index.render(tables)
