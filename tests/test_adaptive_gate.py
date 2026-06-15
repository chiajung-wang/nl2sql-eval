"""Step-6 follow-up (#76): the budget-aware adaptive retrieval gate.

Offline and deterministic: the gate's full-vs-RAG decision is a token-budget
threshold (no LLM), so it is unit-tested directly on ``retrieve`` and through the
import-shared ``run_pipeline`` with the injected FakeAnthropic — never a paid run.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.retrieve import retrieve
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import build_schema_index
from tests.test_pipeline_loop import FakeAnthropic


@pytest.fixture
def store_engine():
    """customers, orders (FK→customers), products, payments — a small store db."""
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(
            text(
                "CREATE TABLE orders ("
                "id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL, "
                "FOREIGN KEY (customer_id) REFERENCES customers(id))"
            )
        )
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(
            text("CREATE TABLE payments (id INTEGER PRIMARY KEY, status TEXT)")
        )
        conn.execute(text("INSERT INTO products VALUES (1, 'Widget')"))
    return engine


def _full_tokens(index) -> int:
    return index.render_tokens([t.name for t in index.tables])


# --- the gate decision (deterministic, no LLM) ------------------------------


def test_gate_dumps_full_schema_when_it_fits_the_budget(store_engine):
    index = build_schema_index(store_engine)
    state = RunState(question="how many products are there?", db_id="store")
    schema = retrieve(state, index, budget_tokens=_full_tokens(index) + 50)
    assert state.retrieval_mode == "full"
    assert set(state.retrieved_tables) == {t.name for t in index.tables}
    # The full dump carries an irrelevant table the RAG path would have dropped.
    assert "CREATE TABLE payments (" in schema


def test_gate_retrieves_when_schema_exceeds_the_budget(store_engine):
    index = build_schema_index(store_engine)
    state = RunState(question="how many products are there?", db_id="store")
    schema = retrieve(state, index, budget_tokens=1)  # nothing fits
    assert state.retrieval_mode == "rag"
    assert state.retrieved_tables == ["products"]
    assert "CREATE TABLE payments (" not in schema


def test_gate_off_without_a_budget_is_the_prior_always_rag(store_engine):
    index = build_schema_index(store_engine)
    state = RunState(question="how many products are there?", db_id="store")
    retrieve(state, index)  # budget_tokens=None → gate disabled
    assert state.retrieval_mode == "rag"
    assert state.retrieved_tables == ["products"]


def test_reretrieve_floor_bypasses_the_gate(store_engine):
    # A widening re-retrieve (floor>0) is always RAG, even if the whole schema
    # would fit the budget — the gate applies to the first pass only.
    index = build_schema_index(store_engine)
    state = RunState(question="how many products are there?", db_id="store")
    retrieve(state, index, floor=2, budget_tokens=_full_tokens(index) + 50)
    assert state.retrieval_mode == "rag"


# --- pipeline wiring (import-shared) ----------------------------------------


def test_run_pipeline_gate_full_sends_the_whole_schema(store_engine):
    index = build_schema_index(store_engine)
    client = FakeAnthropic(reply="SELECT count(*) AS n FROM products")
    state = run_pipeline(
        "how many products are there?",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        budget_tokens=_full_tokens(index) + 50,
    )
    assert state.error is None
    assert state.retrieval_mode == "full"
    sent = client.calls[0]["messages"][0]["content"]
    # Gate dumped everything: even the irrelevant table reached the prompt.
    assert "CREATE TABLE payments (" in sent


def test_run_pipeline_gate_rag_sends_only_relevant_tables(store_engine):
    index = build_schema_index(store_engine)
    client = FakeAnthropic(reply="SELECT count(*) AS n FROM products")
    state = run_pipeline(
        "how many products are there?",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        budget_tokens=1,  # nothing fits → RAG
    )
    assert state.retrieval_mode == "rag"
    sent = client.calls[0]["messages"][0]["content"]
    assert "CREATE TABLE products (" in sent
    assert "CREATE TABLE payments (" not in sent
