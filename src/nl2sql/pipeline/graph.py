"""Stage wiring: the pipeline as a LangGraph state machine.

Step 1 (issue 4) wired a linear ``generate → guard → execute → return``. Step 5
(issue #42) turned that single shot into an **agent**: a capped retry loop that,
on an execution error, feeds the failure back through ``correct`` into a fresh
``generate``. Step 6 (issue #46) made that loop **retrieval-aware**: a not-found
execution error re-retrieves a widened schema (not only regenerates), inside the
same capped budget.

Step 7 (issue #50) re-expresses that *proven* hand-rolled loop as **LangGraph**
nodes + conditional edges. The architecture already *was* a graph — a correction
loop, a retrieval re-trigger, and terminal-state branching — so this is a genuine
fit, not framework-for-its-own-sake. Crucially it is a **behavior-preserving**
refactor: the eval harness numbers must be unchanged, which is exactly what the
harness is for. The two pipeline exits (raw verified result; presented/redacted
result) and every terminal state are untouched — terminal-state classification
still lives in the harness, never here.

The pipeline is import-shared: ``eval/harness.py`` and ``apps/demo/`` both call
``run_pipeline`` with the *same* logic — never a fork. ``run_pipeline`` keeps its
exact signature and ``RunState`` return so no caller changes. Schema text and the
``Engine`` are inputs so this module depends on neither the dataset packages nor
the eval layer.

LangGraph wiring. The mutating run is threaded as a single ``RunState`` channel
(the stage functions mutate it in place, just as before); the loop-local
bookkeeping (``active_schema``, ``allowed_tables``, ``re_retrievals``) rides
alongside it. The static per-run inputs (engine, schema/index, model, client,
budget, …) are passed via ``config["configurable"]`` so the graph compiles once
at import and every question reuses it. Each node returns only the channels it
changed; the conditional edges encode exactly the branches the hand-rolled
``while`` loop had.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.engine import Engine

from nl2sql.obs import stage_span, trace_attributes
from nl2sql.pipeline.correct import correct, correct_literal, correct_soundness
from nl2sql.pipeline.execute import execute
from nl2sql.pipeline.generate import DEFAULT_DIALECT, DEFAULT_MODEL, generate
from nl2sql.pipeline.guard import guard
from nl2sql.pipeline.link import LINK_STRATEGIES, TASK_ALIGNMENT, link_tables
from nl2sql.pipeline.literal_check import literal_check
from nl2sql.pipeline.redact import NO_REDACTION, RedactionPolicy, redact
from nl2sql.pipeline.retrieve import is_not_found_error, missing_identifier, retrieve
from nl2sql.pipeline.soundness import soundness
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import DEFAULT_MAX_TABLES, SchemaIndex
from nl2sql.value_index import ValueIndex

# Single-shot by default (the pass@1 mode): no correction unless a caller opts
# into a budget. The harness raises this for pass@k; the cap is the explicit,
# configurable cost/latency lever the plan calls out.
DEFAULT_MAX_ATTEMPTS = 1


class _GraphState(TypedDict):
    """Channels threaded between LangGraph nodes for one question.

    ``run`` is the mutable ``RunState`` the stage functions write to in place (the
    same object every superstep — LangGraph just carries the reference). The other
    three are the loop-local bookkeeping the hand-rolled ``while`` kept in
    locals: the schema text the next ``generate`` will see, the per-db allowed
    tables for the table-scope guard, and the re-retrieval widening counter.
    """

    run: RunState
    active_schema: str
    allowed_tables: set[str] | None
    re_retrievals: int


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    """Pull the per-run static inputs out of the LangGraph config."""
    return config["configurable"]


# --- nodes ------------------------------------------------------------------


def _init_retrieve(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Initial schema: schema-RAG retrieval, or the naive full dump baseline.

    Mirrors the pre-loop setup of the hand-rolled machine. ``budget_tokens`` arms
    the adaptive gate (#76); ``allowed_tables`` is the per-db scope set, available
    only on the RAG path (``None`` on the naive dump leaves table-scope
    unenforced — it has no index to scope to).

    ``link_strategy == "task_alignment"`` (Step 12, #138) replaces the lexical
    retrieval with schema linking by harvesting generated SQL (``link.link_tables``):
    the model writes SQL against schema variants and the linker unions the tables it
    references. The harvested set is recorded on ``state.retrieved_tables`` exactly
    as RAG records its selection, so retrieval recall scores both the same way.
    Re-retrieval (the scope-widening loop) stays lexical — linking governs only the
    first pass.
    """
    c = _cfg(config)
    run = state["run"]
    index: SchemaIndex | None = c["schema_index"]
    if index is None:
        return {
            "active_schema": c["schema"],
            "allowed_tables": None,
            "re_retrievals": 0,
        }
    allowed_tables: set[str] | None = {t.name for t in index.tables}
    if c.get("link_strategy") == TASK_ALIGNMENT:
        active_schema = _link_retrieve(run, index, c)
    else:
        active_schema = retrieve(
            run,
            index,
            max_tables=c["max_tables"],
            budget_tokens=c["budget_tokens"],
        )
    return {
        "active_schema": active_schema,
        "allowed_tables": allowed_tables,
        "re_retrievals": 0,
    }


def _link_retrieve(run: RunState, index: SchemaIndex, c: dict[str, Any]) -> str:
    """Task-alignment schema linking (#138): harvest tables from generated SQL.

    Builds the ``generate_sql`` callable ``link_tables`` needs by reusing the real
    ``generate`` stage against a throwaway ``RunState`` per variant (so the linking
    generations never clobber the answer state), then folds each linking call's
    token/cost into the run's running totals — a linked retrieval is **not free**,
    so the harness prices the extra generations (the issue's cost-with-the-lift
    rule). Records the harvested tables on ``run.retrieved_tables`` and renders them.
    """
    with stage_span("retrieve", db_id=run.db_id) as extra:

        def generate_sql(schema: str) -> str:
            probe = RunState(question=run.question, db_id=run.db_id)
            generate(
                probe,
                schema,
                dialect=c["dialect"],
                evidence=c["evidence"],
                model=c["model"],
                client=c["client"],
            )
            for key in ("input_tokens", "output_tokens", "cost_usd"):
                if key in probe.meta:
                    run.meta[key] = run.meta.get(key, 0) + probe.meta[key]
            return probe.candidate_sql or ""

        tables = link_tables(
            run.question, index, generate_sql, max_tables=c["max_tables"]
        )
        run.retrieved_tables = tables
        run.retrieval_mode = "link"
        extra["retrieved_tables"] = tables
        extra["n_tables"] = len(tables)
        extra["retrieval_mode"] = "link"
        return index.render(tables)


def _generate(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """One generation cycle: count the attempt, then produce candidate SQL.

    ``state.correction`` (set by a prior ``correct``) feeds the last failure back
    into the prompt; ``None`` on the first attempt.
    """
    c = _cfg(config)
    run = state["run"]
    run.attempts += 1
    generate(
        run,
        state["active_schema"],
        dialect=c["dialect"],
        evidence=c["evidence"],
        model=c["model"],
        client=c["client"],
    )
    return {"run": run}


def _guard(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """The deterministic pre-execution gate (sqlglot AST checks)."""
    guard(
        state["run"],
        dialect=_cfg(config)["dialect"],
        allowed_tables=state["allowed_tables"],
    )
    return {"run": state["run"]}


def _route_after_guard(state: _GraphState, config: RunnableConfig) -> str:
    """Branch on the guard outcome — exactly the hand-rolled decision.

    A table-scope rejection on the RAG path with budget left is the
    *too-narrow-retrieval* symptom: widen and retry (CLAUDE.md §5.4). Any other
    rejection — a security rule, or table-scope with the budget spent — ends the
    run as a terminal guardrail rejection. A clean candidate proceeds to execute.
    """
    run = state["run"]
    if not run.guard_rejected:
        return "soundness"
    c = _cfg(config)
    scope_retry = (
        run.guard_rule == "table_scope"
        and c["schema_index"] is not None
        and run.attempts < c["budget"]
    )
    return "scope_re_retrieve" if scope_retry else END


def _scope_re_retrieve(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Table-scope rejection → clear it and widen the retrieval, then regenerate."""
    c = _cfg(config)
    run = state["run"]
    re_retrievals = state["re_retrievals"] + 1
    run.guard_rejected = False
    run.guard_reason = None
    run.guard_rule = None
    active_schema = retrieve(
        run,
        c["schema_index"],
        max_tables=c["max_tables"],
        floor=c["max_tables"] * 2**re_retrievals,
    )
    return {"run": run, "active_schema": active_schema, "re_retrievals": re_retrievals}


def _soundness(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Deterministic bad-construction scan (Step 12, #139), after a guard-allow.

    Same AST-check shape as the guard but a *correction* contract, not a safety
    gate: it only records a flag on the state; the routing below decides whether the
    budget allows a feed-back retry. ``soundness_enabled=False`` (the ``SOUNDNESS=0``
    A/B arm, #139) skips the scan entirely — the state carries no flag, so routing
    falls straight through to ``literal_check``/``execute``.
    """
    if _cfg(config).get("soundness_enabled", True):
        soundness(state["run"], dialect=_cfg(config)["dialect"])
    return {"run": state["run"]}


def _route_after_soundness(state: _GraphState, config: RunnableConfig) -> str:
    """A clean (or budget-spent) candidate executes; a flagged one with budget left
    feeds the reason back and regenerates.

    A soundness heuristic must never *lose* a run (CLAUDE.md §5 — the checks are
    recoverable signals, not hard rejects): when the retry budget is spent the
    flagged candidate proceeds to ``execute`` anyway, so a false positive costs at
    most a wasted retry, never a dropped answer. The budget test mirrors
    ``_route_after_execute`` so soundness retries share the one capped budget.
    """
    run = state["run"]
    if run.soundness_flag and run.attempts < _cfg(config)["budget"]:
        return "correct_soundness"
    return "literal_check"


def _correct_soundness(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Stage the soundness flag as feedback for the next ``generate``."""
    correct_soundness(state["run"])
    return {"run": state["run"]}


def _literal_check(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Literal→field steering scan (Step 12, #141), after the soundness scan.

    Another post-generation *correction* signal (not a gate): it records a flag when
    a literal is constrained against a column whose sample lacks it. A no-op when no
    value index is configured (the naive-dump / demo path).
    """
    literal_check(
        state["run"], _cfg(config)["value_index"], dialect=_cfg(config)["dialect"]
    )
    return {"run": state["run"]}


def _route_after_literal(state: _GraphState, config: RunnableConfig) -> str:
    """A clean (or budget-spent) candidate executes; an off-column literal with budget
    left feeds the steering message back and regenerates.

    Mirrors ``_route_after_soundness`` — a steering heuristic is a recoverable signal,
    never a hard reject, and shares the one capped budget: a false steer (sampling
    miss) costs at most a wasted retry, never a dropped run.
    """
    run = state["run"]
    if run.literal_flag and run.attempts < _cfg(config)["budget"]:
        return "correct_literal"
    return "execute"


def _correct_literal(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Stage the literal-steering message as feedback for the next ``generate``."""
    correct_literal(state["run"])
    return {"run": state["run"]}


def _execute(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Run the verified candidate against the database."""
    execute(state["run"], _cfg(config)["engine"])
    return {"run": state["run"]}


def _route_after_execute(state: _GraphState, config: RunnableConfig) -> str:
    """A clean result, or a spent budget, ends the run; otherwise correct & retry."""
    run = state["run"]
    if run.error is None or run.attempts >= _cfg(config)["budget"]:
        return END
    return "correct"


def _correct(state: _GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Stage the failure as feedback; re-retrieve when the schema was too narrow.

    A not-found error on the RAG path means the generator saw too little schema —
    route it back into *retrieval* and widen (capture the missing identifier as a
    lexical hint before ``correct`` clears the error), not only into regeneration.
    Otherwise ``correct`` just stages the failure for the next ``generate``. Both
    stay inside the same capped budget enforced by ``_route_after_execute``.
    """
    c = _cfg(config)
    run = state["run"]
    re_retrieve = c["schema_index"] is not None and is_not_found_error(run.error)
    hint = missing_identifier(run.error) if re_retrieve else ""
    correct(run)
    updates: dict[str, Any] = {"run": run}
    if re_retrieve:
        re_retrievals = state["re_retrievals"] + 1
        # Widen coverage each time: max_tables → 2× → 4× …, reaching the full
        # schema at the widest. Bounded by the retry budget above.
        floor = c["max_tables"] * 2**re_retrievals
        updates["active_schema"] = retrieve(
            run,
            c["schema_index"],
            max_tables=c["max_tables"],
            floor=floor,
            hint=hint,
        )
        updates["re_retrievals"] = re_retrievals
    return updates


def _build_graph() -> CompiledStateGraph:
    """Compile the pipeline graph once; ``run_pipeline`` reuses it per question."""
    g = StateGraph(_GraphState)
    g.add_node("init_retrieve", _init_retrieve)
    g.add_node("generate", _generate)
    g.add_node("guard", _guard)
    g.add_node("scope_re_retrieve", _scope_re_retrieve)
    g.add_node("soundness", _soundness)
    g.add_node("correct_soundness", _correct_soundness)
    g.add_node("literal_check", _literal_check)
    g.add_node("correct_literal", _correct_literal)
    g.add_node("execute", _execute)
    g.add_node("correct", _correct)

    g.add_edge(START, "init_retrieve")
    g.add_edge("init_retrieve", "generate")
    g.add_edge("generate", "guard")
    g.add_conditional_edges(
        "guard",
        _route_after_guard,
        {"soundness": "soundness", "scope_re_retrieve": "scope_re_retrieve", END: END},
    )
    g.add_edge("scope_re_retrieve", "generate")
    g.add_conditional_edges(
        "soundness",
        _route_after_soundness,
        {"correct_soundness": "correct_soundness", "literal_check": "literal_check"},
    )
    g.add_edge("correct_soundness", "generate")
    g.add_conditional_edges(
        "literal_check",
        _route_after_literal,
        {"correct_literal": "correct_literal", "execute": "execute"},
    )
    g.add_edge("correct_literal", "generate")
    g.add_conditional_edges(
        "execute", _route_after_execute, {"correct": "correct", END: END}
    )
    g.add_edge("correct", "generate")
    return g.compile()


# Compiled once at import — the wiring is static; only the per-run inputs vary.
_GRAPH = _build_graph()


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
    budget_tokens: int | None = None,
    link_strategy: str | None = None,
    value_index: ValueIndex | None = None,
    soundness_enabled: bool = True,
    redaction_policy: RedactionPolicy = NO_REDACTION,
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
    A guard-allowed candidate then passes the ``soundness`` scan (Step 12, #139):
    deterministic bad-construction checks (NULL-ordering hazard, min/max-by-
    subquery, field catenation) that, unlike the guard, are *correction signals* —
    a flag with budget left feeds its reason back to ``generate``; a flag with the
    budget spent proceeds to ``execute`` anyway (a soundness heuristic never loses a
    run). It then passes the ``literal_check`` scan (Step 12, #141) — the same
    correction contract for the "right value, wrong column" case: when a ``value_index``
    is supplied and a string literal is constrained against a column whose sample
    lacks it (while another column holds it), the steering message naming the right
    columns is fed back to ``generate``. On a clean ``execute`` the run returns
    immediately. On an execution error the ``correct`` stage stages the failure as
    feedback and the loop regenerates, until the candidate succeeds or the
    ``max_attempts`` budget is spent.

    ``max_attempts=1`` (default) is the single-shot pass@1 mode — no correction.
    Returns the populated ``RunState``; scoring and terminal-state classification
    (a budget-exhausted error → ``RETRY_EXHAUSTED``, a single-shot error →
    ``EXECUTION_ERROR_FINAL``) are the harness's job, keyed off ``attempts``.
    ``dialect``/``evidence`` thread into generate, and the same ``dialect``
    parses the candidate in guard (SQLite on the BIRD path; PostgreSQL for the
    payments demo).

    ``budget_tokens`` (schema-RAG path only) arms the **adaptive retrieval gate**
    (#76): when the whole schema fits the configured schema-token budget the
    generator gets the full dump (no retrieval, no dropped tables); when it
    overflows, the ``retrieve`` stage selects the relevant tables. ``None``
    (default) leaves the gate off — the prior always-RAG behaviour. The demo and
    the harness pass the *same* value, so the gate is import-shared, never forked.

    ``link_strategy="task_alignment"`` (schema-RAG path only; Step 12, #138) swaps
    the lexical retrieval for schema linking by harvesting generated SQL (paper
    §3): the generator writes SQL against schema variants and the linker unions the
    tables it references as the focused schema. ``None`` (default) keeps lexical
    RAG. Costs extra generations per question, folded into the run's token/cost
    totals so the harness prices the lift.

    Step 7: the loop above is now executed by a compiled LangGraph state machine
    (``_GRAPH``); the control flow and the ``RunState`` it returns are identical —
    a behavior-preserving refactor the harness verifies.

    Step 8: ``redact`` runs as the final stage and produces the **presented exit**
    (``state.presented_rows``/``presented_columns``) — the raw ``result_rows`` are
    untouched so the harness still scores upstream of redaction (CLAUDE.md §3/§5).
    ``redaction_policy`` is the schema-driven PII column set; the demo and the
    harness pass the *same* policy, so the presented exit is import-shared, never
    forked. The default :data:`NO_REDACTION` masks nothing (the BIRD path).
    """
    if (schema is None) == (schema_index is None):
        raise ValueError("run_pipeline needs exactly one of schema= or schema_index=")
    # Validate the strategy up front: an unrecognized name (a typo like
    # "task_alignmnet") must raise, not silently run lexical RAG — a silent fallback
    # would misattribute the measured A/B (CLAUDE.md §6 traceability). ``None`` is the
    # no-linking default and is always allowed. Mirrors ``link_tables``' own raise on
    # an unknown variant, so the strategy and variant selectors are equally strict.
    if link_strategy is not None and link_strategy not in LINK_STRATEGIES:
        raise ValueError(f"unknown link_strategy: {link_strategy!r}")
    budget = max(1, max_attempts)
    # Name and tag the trace so a run is findable/filterable in the Langfuse UI
    # (db and model are the cross-provider / single-db filter axes, CLAUDE.md §5.8).
    # ``trace_input`` records the NL question as the trace's input; the result-shape
    # below is its output — never raw rows (CLAUDE.md §5.3).
    with (
        trace_attributes(trace_name="nl2sql", tags=[f"db:{db_id}", f"model:{model}"]),
        stage_span(
            "pipeline",
            trace_input=question,
            db_id=db_id,
            model=model,
            max_attempts=budget,
        ) as extra,
    ):
        state = RunState(question=question, db_id=db_id, max_attempts=budget)
        config: RunnableConfig = {
            "configurable": {
                "schema": schema,
                "schema_index": schema_index,
                "engine": engine,
                "dialect": dialect,
                "evidence": evidence,
                "model": model,
                "client": client,
                "max_tables": max_tables,
                "budget_tokens": budget_tokens,
                "link_strategy": link_strategy,
                "value_index": value_index,
                "soundness_enabled": soundness_enabled,
                "budget": budget,
            },
            # Each attempt costs a few supersteps (generate→guard→soundness→
            # literal_check→execute, plus a correct / correct_soundness /
            # correct_literal hop on a retry); size the ceiling to the budget so a
            # legitimate pass@k run never trips LangGraph's recursion guard, while a
            # genuine wiring bug (an unbounded loop) still surfaces.
            "recursion_limit": budget * 10 + 25,
        }
        result = _GRAPH.invoke({"run": state}, config=config)
        run: RunState = result["run"]
        # The second pipeline exit: mask PII into the presented result, leaving the
        # raw verified result the harness scores untouched (CLAUDE.md §3/§5.2).
        redact(run, redaction_policy)
        # Trace output: the *presented* (redacted) result's shape and the generated
        # SQL — counts and flags only, never raw rows (CLAUDE.md §5.3). This is what
        # makes the trace legible at the root: question in, result-shape + SQL out.
        extra["candidate_sql"] = run.candidate_sql
        extra["presented_row_count"] = (
            len(run.presented_rows) if run.presented_rows is not None else 0
        )
        extra["presented_column_count"] = (
            len(run.presented_columns) if run.presented_columns is not None else 0
        )
        extra["attempts"] = run.attempts or 1
        extra["guard_rejected"] = run.guard_rejected
        return run


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
