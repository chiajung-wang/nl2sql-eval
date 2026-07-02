"""Load BIRD questions and connect each to its tagged SQLite database.

BIRD ships SQLite, **file-per-db**: ``dev.json`` holds the questions (each tagged
with its ``db_id``) and ``dev_databases/<db_id>/<db_id>.sqlite`` is that db. The
db identity is an *input* — every question runs against its own tagged db
(single-db per run; cross-db routing is out of scope, CLAUDE.md §5.8).

The benchmark data is downloaded separately and gitignored; ``BIRD_DATA_DIR``
points at the ``dev`` directory (default: the in-repo ``data/`` folder). Engines
open the db **read-only** — the harness only reads, and a model-generated
candidate must never mutate a benchmark db.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def bird_data_dir() -> Path:
    """Resolve the BIRD data directory from ``BIRD_DATA_DIR`` (or the default)."""
    raw = os.environ.get("BIRD_DATA_DIR")
    return Path(raw).expanduser().resolve() if raw else DEFAULT_DATA_DIR


def load_dev_questions(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load every BIRD dev question (``question_id``, ``db_id``, ``question``,
    ``SQL``, ``difficulty``, ``evidence``) from ``dev.json``."""
    data_dir = data_dir or bird_data_dir()
    return json.loads((data_dir / "dev.json").read_text())


def load_minidev_questions(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load the BIRD **Mini-Dev** SQLite subset (same fields as
    :func:`load_dev_questions`) from ``mini_dev_sqlite.json``.

    Mini-Dev (github.com/bird-bench/mini_dev, HuggingFace ``birdsql/bird_mini_dev``)
    is a 500-question, hand-curated, difficulty-stratified (30/50/20
    simple/moderate/challenging) subset of this same dev pool, drawn from the same
    11 dbs already under ``dev_databases/`` — no extra db download needed. Use this
    loader rather than filtering ``load_dev_questions()`` by id: Mini-Dev corrects
    the gold ``SQL`` for a minority of questions versus the original ``dev.json``
    (community-reported fixes), so re-deriving from ``dev.json`` would silently
    score against the stale gold on those rows.
    """
    data_dir = data_dir or bird_data_dir()
    return json.loads((data_dir / "mini_dev_sqlite.json").read_text())


def db_path(db_id: str, data_dir: Path | None = None) -> Path:
    """Filesystem path to a tagged db's SQLite file."""
    data_dir = data_dir or bird_data_dir()
    return data_dir / "dev_databases" / db_id / f"{db_id}.sqlite"


def get_engine(db_id: str, data_dir: Path | None = None) -> Engine:
    """A **read-only** SQLAlchemy engine for one tagged BIRD db.

    Read-only by design: the harness only reads, and a model-generated candidate
    SQL must never be able to mutate a benchmark database.
    """
    path = db_path(db_id, data_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"BIRD db {db_id!r} not found at {path} — "
            "is BIRD_DATA_DIR set and the data downloaded?"
        )
    return create_engine(f"sqlite:///file:{path}?mode=ro&uri=true")


def schema_text(engine: Engine) -> str:
    """The db's DDL — the ``CREATE TABLE`` statements, dumped for the prompt.

    This is the *naive schema dump* the generator sees with no retrieval yet
    (Step 6 replaces it with schema-RAG). Tables are emitted in name order so the
    dump is stable across runs.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND sql IS NOT NULL ORDER BY name"
            )
        )
        return "\n\n".join(r[0] for r in rows)


def run_query(
    engine: Engine, sql: str, *, timeout: float | None = None
) -> dict[str, Any]:
    """Execute ``sql`` and return a comparator-shaped ``{"columns", "rows"}``.

    The primitive the harness uses to materialize a gold (or candidate) result
    set from a BIRD db for scoring via ``eval/compare.py``.

    ``timeout`` (seconds) bounds wall-clock execution via SQLite's progress
    handler, which aborts the query (raising ``OperationalError``) once the
    deadline passes — including during ``fetchall``. Default ``None`` keeps the
    original unbounded behavior for the harness's gold queries; callers that
    execute *untrusted* candidate SQL (e.g. ``diagnose_bird`` re-scoring a model
    that may emit a runaway cross-join) pass a timeout so a single pathological
    query can't hang the run. The handler fires every ``n`` VM ops, so the abort
    is coarse (op-count, not a hard real-time guarantee) but reliably bounded.
    """
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection if timeout is not None else None
        if raw is not None:
            deadline = time.monotonic() + timeout
            raw.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0, 10_000
            )
        try:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [tuple(row) for row in result.fetchall()]
        finally:
            if raw is not None:
                raw.set_progress_handler(None, 10_000)
    return {"columns": columns, "rows": rows}


def table_count(engine: Engine) -> int:
    """Number of user tables in a db — the schema-size proxy used to pick the
    small-schema slice (CLAUDE.md §5.9 rationale: avoid context overflow)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT count(*) FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        return int(rows.scalar_one())


def schema_table_counts(
    db_ids: Sequence[str], data_dir: Path | None = None
) -> dict[str, int]:
    """Map each db to its user-table count (for slice selection)."""
    counts: dict[str, int] = {}
    for db_id in db_ids:
        engine = get_engine(db_id, data_dir)
        try:
            counts[db_id] = table_count(engine)
        finally:
            engine.dispose()
    return counts
