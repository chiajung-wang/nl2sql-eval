"""Schema enrichment — FK surfacing + sample rows, offline (in-memory SQLite).

Pins the deterministic enrichment the Step-11 schema A/B depends on: foreign keys
extracted and de-duplicated (with the implicit-PK parent column resolved), sample
rows truncated, and the assembled enriched schema carrying both new sections on
top of the DDL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from eval.datasets.bird.enrich import (
    enriched_schema,
    foreign_keys,
    sample_rows,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", future=True)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT)"))
        # explicit parent column, and an implicit-PK reference to exercise resolution
        conn.execute(
            text(
                "CREATE TABLE child (id INTEGER, pid INTEGER, "
                "FOREIGN KEY (pid) REFERENCES parent(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE grandchild (id INTEGER, cid INTEGER, "
                "FOREIGN KEY (cid) REFERENCES parent)"  # no parent column → implicit PK
            )
        )
        conn.execute(text("INSERT INTO parent VALUES (1, 'alice'), (2, 'bob')"))
        conn.execute(text("INSERT INTO child VALUES (10, 1), (11, 2)"))
    return eng


def test_foreign_keys_extracted_and_implicit_pk_resolved(engine):
    fks = foreign_keys(engine)
    assert ("child", "pid", "parent", "id") in fks
    # the implicit-PK reference resolves the NULL parent column to the real PK
    assert ("grandchild", "cid", "parent", "id") in fks


def test_foreign_keys_are_sorted_and_deduped(engine):
    fks = foreign_keys(engine)
    assert fks == sorted(set(fks))


def test_sample_rows_truncates_wide_cells(engine):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO parent VALUES (3, '" + "x" * 100 + "')"))
    rows = sample_rows(engine, n=5, max_cell=40)
    cols, parent_rows = rows["parent"]
    assert cols == ["id", "name"]
    wide = [r[1] for r in parent_rows if str(r[1]).startswith("x")][0]
    assert len(wide) <= 41 and wide.endswith("…")


def test_enriched_schema_carries_ddl_plus_both_sections(engine):
    s = enriched_schema(engine)
    assert "CREATE TABLE" in s  # the DDL is still there
    assert "Foreign-key relationships" in s
    assert "child.pid -> parent.id" in s
    assert "Sample rows" in s
    assert "alice" in s  # a real value format surfaced
