"""Schema-RAG (Step 6, issue #45) — index build, lexical retrieval, pipeline wiring.

Offline and deterministic: the index is built from an in-memory SQLite db and the
retriever scores by lexical overlap (no embeddings, no network). The pipeline
wiring is exercised with the injected FakeLLMClient so we can assert the generator
saw only the *relevant* tables, never the full dump.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.retrieve import retrieve
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import (
    ColumnMeta,
    SchemaIndex,
    TableMeta,
    build_schema_index,
    estimate_tokens,
)
from tests.test_pipeline_loop import FakeLLMClient


@pytest.fixture
def store_engine():
    """A small store schema: customers, orders (FK→customers), products, payments.

    ``payments.status`` carries enum-like sample values so a question mentioning
    "settled" can find it by value, not just by name.
    """
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
        conn.execute(text("INSERT INTO customers VALUES (1, 'Ada'), (2, 'Bo')"))
        conn.execute(text("INSERT INTO orders VALUES (1, 1, 9.0), (2, 2, 4.0)"))
        conn.execute(text("INSERT INTO payments VALUES (1, 'settled'), (2, 'failed')"))
    return engine


# --- index construction -----------------------------------------------------


def test_build_index_captures_tables_columns_fks_and_samples(store_engine):
    index = build_schema_index(store_engine)
    by_name = index.by_name()

    assert set(by_name) == {"customers", "orders", "products", "payments"}
    # Columns + types introspected.
    cols = {c.name for c in by_name["orders"].columns}
    assert {"id", "customer_id", "total"} <= cols
    # Foreign key edge captured (local_col, referred_table).
    assert ("customer_id", "customers") in by_name["orders"].foreign_keys
    # Enum-like sample values captured for the status column.
    status = next(c for c in by_name["payments"].columns if c.name == "status")
    assert set(status.sample_values) == {"settled", "failed"}


def test_build_index_is_stable_and_sorted(store_engine):
    a = build_schema_index(store_engine)
    b = build_schema_index(store_engine)
    assert [t.name for t in a.tables] == [t.name for t in b.tables]
    assert [t.name for t in a.tables] == sorted(t.name for t in a.tables)


def test_samples_capture_enum_value_buried_past_a_row_prefix():
    # A low-cardinality enum whose *second* value only appears far down the table:
    # a row-prefix scan would miss "settled"; SELECT DISTINCT surfaces it.
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, status TEXT)"))
        conn.execute(
            text("INSERT INTO t (status) VALUES (:s)"),
            [{"s": "failed"} for _ in range(500)] + [{"s": "settled"}],
        )
    index = build_schema_index(engine)
    status = next(c for c in index.by_name()["t"].columns if c.name == "status")
    assert set(status.sample_values) == {"failed", "settled"}


def test_samples_are_capped_at_requested_limit():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, code TEXT)"))
        conn.execute(
            text("INSERT INTO t (code) VALUES (:c)"),
            [{"c": f"c{i}"} for i in range(50)],
        )
    index = build_schema_index(engine, sample_values=3)
    code = next(c for c in index.by_name()["t"].columns if c.name == "code")
    assert len(code.sample_values) == 3


# --- lexical retrieval -------------------------------------------------------


def test_relevant_tables_picks_table_by_name(store_engine):
    index = build_schema_index(store_engine)
    assert index.relevant_tables("how many products are there?") == ["products"]


def test_relevant_tables_matches_sample_value_not_just_name(store_engine):
    # "settled" appears nowhere in a table/column name — only as a payments.status
    # value. The sample-value signal is what makes the SQL correct (status enum).
    index = build_schema_index(store_engine)
    assert "payments" in index.relevant_tables("count settled transactions")


def test_relevant_tables_expands_to_fk_neighbours(store_engine):
    # A question about orders needs customers too (the join target) — FK expansion.
    index = build_schema_index(store_engine)
    tables = index.relevant_tables("total of orders per customer")
    assert "orders" in tables and "customers" in tables


def test_relevant_tables_respects_max_tables_budget(store_engine):
    index = build_schema_index(store_engine)
    # Two name hits, but the budget caps the ranked picks at one (FK neighbours
    # of that one may still ride along — never the unrelated tables).
    tables = index.relevant_tables("customers and products", max_tables=1)
    assert "products" not in tables or "customers" not in tables


def test_no_lexical_signal_falls_back_to_full_schema(store_engine):
    # Nothing matches → degrade to every table (never worse than the naive dump).
    index = build_schema_index(store_engine)
    assert index.relevant_tables("zzzqux nothing matches") == [
        "customers",
        "orders",
        "payments",
        "products",
    ]


def test_relevant_tables_preserves_declaration_order(store_engine):
    index = build_schema_index(store_engine)
    order = [t.name for t in index.tables]
    tables = index.relevant_tables("orders and customers and payments")
    assert tables == sorted(tables, key=order.index)


def test_floor_widens_a_narrow_retrieval_padding_from_declaration_order(store_engine):
    # The re-retrieve lever (#46): one lexical hit, but floor=3 pads two more
    # tables from declaration order. The ranked pick is always kept.
    index = build_schema_index(store_engine)
    tables = index.relevant_tables("products", max_tables=1, floor=3)
    assert "products" in tables
    assert len(tables) == 3


def test_floor_beyond_table_count_reaches_the_full_schema(store_engine):
    index = build_schema_index(store_engine)
    tables = index.relevant_tables("products", max_tables=1, floor=99)
    assert tables == ["customers", "orders", "payments", "products"]


def test_floor_pads_even_with_no_lexical_signal(store_engine):
    # No table scores, but a floor still yields a bounded set (not the full dump).
    index = build_schema_index(store_engine)
    tables = index.relevant_tables("zzzqux nothing", max_tables=2, floor=2)
    assert len(tables) == 2


def test_floor_below_selection_is_a_noop(store_engine):
    index = build_schema_index(store_engine)
    assert index.relevant_tables("products", max_tables=1, floor=1) == ["products"]


# --- rendering --------------------------------------------------------------


def test_render_emits_create_table_with_samples_and_fks():
    index = SchemaIndex(
        (
            TableMeta(
                "payments",
                (
                    ColumnMeta("id", "INTEGER"),
                    ColumnMeta("status", "TEXT", ("failed", "settled")),
                    ColumnMeta("order_id", "INTEGER"),
                ),
                foreign_keys=(("order_id", "orders"),),
            ),
        )
    )
    rendered = index.render(["payments"])
    assert "CREATE TABLE payments (" in rendered
    assert "status TEXT" in rendered
    assert "FOREIGN KEY (order_id) REFERENCES orders" in rendered
    assert "status ∈ {failed, settled}" in rendered


def test_render_skips_unknown_table_names():
    index = SchemaIndex((TableMeta("t", (ColumnMeta("id", "INT"),)),))
    assert index.render(["nope"]) == ""


# --- retrieve stage ---------------------------------------------------------


def test_retrieve_records_selected_tables_on_state(store_engine):
    index = build_schema_index(store_engine)
    state = RunState(question="how many products?", db_id="store")

    schema = retrieve(state, index)

    assert state.retrieved_tables == ["products"]
    assert "CREATE TABLE products (" in schema
    # The focused schema excludes the irrelevant tables.
    assert "CREATE TABLE payments (" not in schema


# --- pipeline wiring --------------------------------------------------------


def test_run_pipeline_feeds_only_retrieved_tables_to_generate(store_engine):
    index = build_schema_index(store_engine)
    client = FakeLLMClient(reply="SELECT count(*) AS n FROM products")

    state = run_pipeline(
        "how many products are there?",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
    )

    assert state.error is None
    assert state.retrieved_tables == ["products"]
    sent = client.calls[0]["messages"][0]["content"]
    assert "CREATE TABLE products (" in sent
    # The naive full dump is gone: an unrelated table never reached the prompt.
    assert "CREATE TABLE payments (" not in sent


def test_run_pipeline_requires_exactly_one_schema_source(store_engine):
    index = build_schema_index(store_engine)
    with pytest.raises(ValueError):
        run_pipeline("q", engine=store_engine)  # neither
    with pytest.raises(ValueError):
        run_pipeline(  # both
            "q",
            schema="CREATE TABLE t (id INT)",
            schema_index=index,
            engine=store_engine,
        )


# --- schema-token budget (Step-6 follow-up #75) -----------------------------


def test_estimate_tokens_is_ceil_chars_over_four():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1  # ceil(1/4)
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2  # ceil(5/4)


def test_ranked_names_orders_by_relevance_then_declaration(store_engine):
    index = build_schema_index(store_engine)
    ranked = index.ranked_names("how many products are there?")
    # Every table is present (ranking never truncates) …
    assert set(ranked) == {"customers", "orders", "payments", "products"}
    # … and the lexical hit leads.
    assert ranked[0] == "products"


def test_ranked_names_ties_break_by_declaration_order(store_engine):
    index = build_schema_index(store_engine)
    # No lexical signal → all scores tie at 0 → declaration order preserved.
    assert index.ranked_names("zzzqux nothing matches") == [
        t.name for t in index.tables
    ]


def test_fit_budget_keeps_priority_prefix_within_budget(store_engine):
    index = build_schema_index(store_engine)
    ranked = index.ranked_names("how many products are there?")
    # A generous budget keeps everything …
    assert set(index.fit_budget(ranked, 10_000)) == {
        "customers",
        "orders",
        "payments",
        "products",
    }
    # … a tight budget keeps fewer, and the top-ranked table survives.
    tight = index.fit_budget(ranked, index.render_tokens(["products"]))
    assert "products" in tight
    assert len(tight) < 4


def test_fit_budget_always_keeps_at_least_one_table(store_engine):
    index = build_schema_index(store_engine)
    ranked = index.ranked_names("how many products are there?")
    # Even a zero budget never starves the generator of all schema.
    kept = index.fit_budget(ranked, 0)
    assert kept == ["products"]


def test_fit_budget_returns_declaration_order(store_engine):
    index = build_schema_index(store_engine)
    order = [t.name for t in index.tables]
    # Relevance-ordered input, but the rendered selection is declaration-ordered.
    kept = index.fit_budget(index.ranked_names("orders and customers"), 10_000)
    assert kept == sorted(kept, key=order.index)
