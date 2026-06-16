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

import re

from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import DEFAULT_MAX_TABLES, SchemaIndex

# Default schema-token budget for the adaptive gate (#76) — the explicit config
# key, not a magic number inline. It is a *cost/latency policy* on how much schema
# rides in each prompt, not the model's context limit. 2048 sits in the regime the
# #75 sweep mapped: the smaller BIRD dbs fit it (gate → full dump, recovering the
# accuracy schema-RAG's table cap gave up), while the largest overflow it (gate →
# RAG). ``budget_tokens=None`` leaves the gate off (the prior always-RAG path).
DEFAULT_SCHEMA_TOKEN_BUDGET = 2048


def schema_fits_budget(index: SchemaIndex, budget_tokens: int) -> bool:
    """True if the *whole* schema renders within ``budget_tokens``.

    The single source of truth for the adaptive gate's full-vs-RAG decision —
    used both here (to route a run) and by the eval harness (to report, offline,
    how the gate would route each case), so the threshold is defined once."""
    return index.render_tokens([t.name for t in index.tables]) <= budget_tokens


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

# The identifier the engine reported as missing — SQLite "no such table: ghost"
# or PostgreSQL 'relation "ghost" does not exist'. Pulled from the *error string*
# (not the SQL) so the re-retrieve hint is the name the generator reached for,
# rather than the message's stopwords.
_MISSING_IDENT_RE = re.compile(
    r"no such (?:table|column):\s*([^\s).,]+)" r'|"([^"]+)"\s+does not exist'
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


def missing_identifier(error: str | None) -> str:
    """The missing table/column name(s) from a not-found ``error``, space-joined.

    The re-retrieve's lexical hint: the bare identifier the generator reached for
    (``ghost``), not the whole message — so the hint is signal, not stopwords like
    "no such table". Empty when nothing parses out (widening still does the heavy
    lifting). Parses the error *string*, never the SQL.
    """
    if not error:
        return ""
    names = [a or b for a, b in _MISSING_IDENT_RE.findall(error)]
    return " ".join(dict.fromkeys(n for n in names if n))


def retrieve(
    state: RunState,
    index: SchemaIndex,
    *,
    max_tables: int = DEFAULT_MAX_TABLES,
    floor: int = 0,
    hint: str = "",
    budget_tokens: int | None = None,
) -> str:
    """Select the relevant tables for ``state.question`` and render their schema.

    Records the chosen table names on ``state.retrieved_tables`` (for the recall
    metric) and returns the focused schema string the generator consumes.
    ``floor`` is the **primary** re-retrieve lever: it widens coverage to at least
    that many tables (padding from declaration order) so a re-retrieve surfaces
    more of the schema than the first attempt. ``hint`` (the missing identifier
    from the prior not-found error) is a secondary nudge folded into the lexical
    query — it helps only when the reached-for name lexically resembles a real
    table. Only table *names* and counts reach the span — schema metadata, never
    result rows.

    **Adaptive gate (#76).** When ``budget_tokens`` is set and this is the initial
    retrieval (``floor == 0`` and no ``hint``), the gate checks whether the *whole*
    schema fits the budget; if it does it dumps the full schema
    (``retrieval_mode = "full"``) rather than retrieving, because retrieval can
    only *drop* a needed table when everything already fits — the Step-6 −0.125
    mechanism. When the full schema exceeds the budget it falls back to RAG, and
    that selection is **fit to the budget** (``fit_budget``), not a table count —
    so the gate is a genuine per-call cost ceiling: the rendered schema never
    exceeds the budget (modulo a single table larger than the budget, always
    kept). The decision is deterministic and threshold-driven (no LLM);
    re-retrievals (``floor > 0``) are always RAG-widening by table count, so the
    gate applies to the first pass only. With ``budget_tokens=None`` the gate is
    off and behaviour is the prior always-RAG (``relevant_tables``, table-capped).
    """
    with stage_span("retrieve", db_id=state.db_id) as extra:
        full = [t.name for t in index.tables]
        gate_open = budget_tokens is not None and floor == 0 and not hint
        if gate_open and schema_fits_budget(index, budget_tokens):
            tables, mode = full, "full"
        elif gate_open:
            # Gate routed to RAG because the full schema exceeds the budget. Bound
            # the selection by the *budget* (not max_tables) so the gate actually
            # enforces the cost ceiling it promises.
            tables = index.fit_budget(index.ranked_names(state.question), budget_tokens)
            mode = "rag"
        else:
            query = f"{state.question} {hint}".strip() if hint else state.question
            tables = index.relevant_tables(query, max_tables=max_tables, floor=floor)
            mode = "rag"
        state.retrieved_tables = tables
        state.retrieval_mode = mode
        extra["retrieved_tables"] = tables
        extra["n_tables"] = len(tables)
        extra["retrieval_mode"] = mode
        if budget_tokens is not None:
            extra["budget_tokens"] = budget_tokens
        if floor:
            extra["floor"] = floor
        return index.render(tables)
