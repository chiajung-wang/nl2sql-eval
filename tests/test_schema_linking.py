"""Task-alignment schema linking (Step 12, #138) — offline unit coverage.

The deterministic core of the lever the AT&T paper (arXiv:2505.19988v2 §3) used to
beat table selection: harvest the tables a *generated* SQL references and union
across schema variants. Everything here runs with an injected fake generator — no
network, no API key — proving the harvesting, union, declaration-order, and
degrade-never-starve behaviour offline; the live A/B is deferred (gated on a key).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.link import link_tables, tables_in_sql
from nl2sql.schema_index import ColumnMeta, SchemaIndex, TableMeta, build_schema_index
from tests.test_pipeline_loop import FakeLLMClient


def _index() -> SchemaIndex:
    """A 3-table store index in a deliberate declaration order.

    Order is customers, orders, products — so declaration-order assertions are
    distinguishable from alphabetical or harvest order."""
    return SchemaIndex(
        (
            TableMeta(
                "customers", (ColumnMeta("id", "INTEGER"), ColumnMeta("name", "TEXT"))
            ),
            TableMeta(
                "orders",
                (ColumnMeta("id", "INTEGER"), ColumnMeta("customer_id", "INTEGER")),
                (("customer_id", "customers"),),
            ),
            TableMeta(
                "products", (ColumnMeta("id", "INTEGER"), ColumnMeta("title", "TEXT"))
            ),
        )
    )


# --- tables_in_sql: the deterministic harvesting primitive ------------------


def test_harvest_join_returns_both_base_tables():
    sql = "SELECT * FROM orders JOIN customers ON orders.customer_id = customers.id"
    assert tables_in_sql(sql) == {"orders", "customers"}


def test_harvest_sees_through_aliases():
    sql = "SELECT o.id FROM orders AS o JOIN customers AS c ON o.customer_id = c.id"
    assert tables_in_sql(sql) == {"orders", "customers"}


def test_harvest_excludes_cte_names_keeps_real_tables():
    sql = (
        "WITH recent AS (SELECT * FROM orders) "
        "SELECT * FROM recent JOIN customers ON recent.customer_id = customers.id"
    )
    # ``recent`` is a CTE, not a base table the retriever could surface.
    assert tables_in_sql(sql) == {"orders", "customers"}


def test_harvest_includes_subquery_tables():
    sql = "SELECT * FROM customers WHERE id IN (SELECT customer_id FROM orders)"
    assert tables_in_sql(sql) == {"orders", "customers"}


def test_harvest_is_casefolded():
    assert tables_in_sql("SELECT * FROM Orders") == {"orders"}


def test_harvest_unparseable_sql_returns_empty_not_raises():
    assert tables_in_sql("this is not sql at all") == set()
    assert tables_in_sql("") == set()


def test_harvest_string_literal_named_like_a_table_not_counted():
    # The word "from" inside a literal must not be read as a table — AST, not regex.
    sql = "SELECT * FROM customers WHERE name = 'select from orders'"
    assert tables_in_sql(sql) == {"customers"}


# --- link_tables: variant union, drop, degrade -----------------------------


def test_link_unions_harvested_tables_in_declaration_order():
    index = _index()
    sql = "SELECT * FROM orders JOIN customers ON orders.customer_id = customers.id"
    linked = link_tables("anything", index, lambda _schema: sql)
    # Declaration order is customers, orders — not harvest/alpha order.
    assert linked == ["customers", "orders"]


def test_link_harvests_a_table_lexical_rag_would_miss():
    """The point of task-alignment: tables come from the *generated SQL*, not lexical
    overlap — so a table the question never names is still linked if the SQL uses it."""
    index = _index()
    # A question with no lexical overlap with "customers", yet the SQL joins it.
    linked = link_tables(
        "show me everything",
        index,
        lambda _schema: (
            "SELECT * FROM orders JOIN customers ON orders.customer_id = customers.id"
        ),
    )
    assert "customers" in linked


def test_link_drops_hallucinated_tables_not_in_schema():
    index = _index()
    linked = link_tables(
        "q",
        index,
        lambda _schema: "SELECT * FROM orders JOIN ghosts ON orders.id = ghosts.id",
    )
    assert linked == ["orders"]  # ``ghosts`` isn't a real table — dropped.


def test_link_degrades_to_lexical_rag_when_nothing_harvested():
    index = _index()
    # Every variant generation is unusable → fall back to lexical RAG, never empty.
    linked = link_tables("orders for a customer", index, lambda _schema: "not sql")
    assert linked == index.relevant_tables("orders for a customer")
    assert linked  # never starves the generator


def test_link_variant_generation_failure_is_nonfatal():
    index = _index()
    calls = {"n": 0}

    def flaky(_schema: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider blip on the first variant")
        return "SELECT * FROM products"

    linked = link_tables("q", index, flaky)
    assert linked == ["products"]  # second variant still contributed
    assert calls["n"] == 2  # both variants were attempted


def test_link_respects_a_single_variant():
    index = _index()
    seen: list[str] = []

    def gen(schema: str) -> str:
        seen.append(schema)
        return "SELECT * FROM products"

    link_tables("q", index, gen, variants=("full",))
    assert len(seen) == 1  # only one variant generated against


def test_link_unknown_variant_raises():
    with pytest.raises(ValueError, match="unknown schema-link variant"):
        link_tables("q", _index(), lambda _s: "SELECT 1", variants=("bogus",))


# --- graph wiring: link_strategy threads through run_pipeline ----------------


@pytest.fixture
def store_engine():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(
            text(
                "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, "
                "FOREIGN KEY (customer_id) REFERENCES customers(id))"
            )
        )
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'Ada')"))
        conn.execute(text("INSERT INTO orders VALUES (1, 1)"))
    return engine


def test_run_pipeline_task_alignment_records_harvested_tables(store_engine):
    index = build_schema_index(store_engine)
    sql = "SELECT c.name FROM orders o JOIN customers c ON o.customer_id = c.id"
    client = FakeLLMClient(sql)
    state = run_pipeline(
        "names of customers with orders",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        link_strategy="task_alignment",
    )
    assert state.retrieval_mode == "link"
    assert state.retrieved_tables == ["customers", "orders"]  # declaration order, union


def test_task_alignment_folds_linking_cost_into_run_totals(store_engine):
    index = build_schema_index(store_engine)
    client = FakeLLMClient("SELECT * FROM orders")
    state = run_pipeline(
        "orders",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        link_strategy="task_alignment",
    )
    # Two linking generations (focused + full) + one answer generation = 3 calls,
    # all priced: FakeLLMClient reports 11 in / 7 out per call.
    assert len(client.calls) == 3
    assert state.meta["input_tokens"] == 33
    assert state.meta["output_tokens"] == 21


def test_default_strategy_is_unchanged_lexical_rag(store_engine):
    index = build_schema_index(store_engine)
    client = FakeLLMClient("SELECT * FROM orders")
    state = run_pipeline(
        "orders for a customer",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
    )
    # No link_strategy → the prior lexical RAG path, one generation only.
    assert state.retrieval_mode == "rag"
    assert len(client.calls) == 1
