"""Stage: retrieve — schema-RAG over table/column metadata + sample values.

Replaces the Step-3 naive full-schema dump: score the db's tables against *this*
question (deterministic lexical overlap, see ``nl2sql.schema_index``) and hand
``generate`` only the relevant tables' definitions instead of every table. The
selected table names are recorded on the state so the harness can measure
**retrieval recall** against the gold query's tables (a later Step-6 slice).

**Loop-aware (Step 6, issue #46).** A ``column/table-not-found`` execution error
routes back into *retrieval*, not only generation: the graph re-retrieves with a
widened ``floor`` (and the error as a lexical hint) so a too-narrow first
retrieval can recover by surfacing more of the schema — culminating, at the
widest, in the full dump. ``is_not_found_error`` classifies the error string (an
engine *message*, not SQL — sqlglot governs SQL semantics elsewhere). The
re-retrieve stays inside the Step-5 capped budget; it is not a budget bypass.

The pipeline is import-shared — the harness and the demo build the index and call
this the same way, never a fork.
"""

from __future__ import annotations

from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import DEFAULT_MAX_TABLES, SchemaIndex

# Substrings that mark a not-found-class execution error across the engines we
# run: SQLite ("no such table/column: x"), PostgreSQL ('relation/column "x" does
# not exist'). Matching the message — not the SQL — so this is plain string
# classification, deterministic, no LLM/regex-for-semantics (CLAUDE.md §4/§7).
_NOT_FOUND_MARKERS = (
    "no such table",
    "no such column",
    "does not exist",
    "unknown column",
)


def is_not_found_error(error: str | None) -> bool:
    """True if ``error`` is a missing-table/column error — the re-retrieve signal.

    These are the failures retrieval can plausibly fix (the generator reached for
    something the schema it saw didn't contain); other errors (syntax, type) are
    left to plain regeneration.
    """
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in _NOT_FOUND_MARKERS)


def retrieve(
    state: RunState,
    index: SchemaIndex,
    *,
    max_tables: int = DEFAULT_MAX_TABLES,
    floor: int = 0,
    hint: str = "",
) -> str:
    """Select the relevant tables for ``state.question`` and render their schema.

    Records the chosen table names on ``state.retrieved_tables`` (for the recall
    metric) and returns the focused schema string the generator consumes. ``hint``
    (the prior not-found error text on a re-retrieve) is folded into the lexical
    query as extra context; ``floor`` widens coverage to at least that many tables
    (padding from declaration order) so a re-retrieve surfaces more of the schema
    than the first attempt. Only table *names* and counts reach the span — schema
    metadata, never result rows.
    """
    with stage_span("retrieve", db_id=state.db_id) as extra:
        query = f"{state.question} {hint}".strip() if hint else state.question
        tables = index.relevant_tables(query, max_tables=max_tables, floor=floor)
        state.retrieved_tables = tables
        extra["retrieved_tables"] = tables
        extra["n_tables"] = len(tables)
        if floor:
            extra["floor"] = floor
        return index.render(tables)
