"""Schema **enrichment**: surface the join paths and value formats the model misses.

The Step-11 error analysis (#111) found the dominant genuine-failure bucket is
**wrong tables / wrong join path** — even though the foreign keys are technically
present in the naive DDL dump, they are buried at the bottom of long
``CREATE TABLE`` statements where the model doesn't use them. This builds an
**enriched schema** that keeps the DDL but *surfaces*:

1. a concise **foreign-key relationships** section (the join paths, made salient), and
2. a few **sample rows** per table (so the model knows value spellings/formats —
   the diagnostic's "wrong categorical value" failures, e.g. a date stored as
   ``'201207'``).

It is a schema-*representation* lever (like Step 6's retrieval), not a prompt
edit: the enriched text flows through the existing ``schema`` input, so the A/B is
naive-dump vs enriched, same template, same model. **BIRD-only** (a public
benchmark, no PII) — never point sample-row dumping at a PII schema like payments.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from eval.datasets.bird.loader import schema_text

_MAX_CELL = 40  # truncate a sample value so a wide TEXT column can't bloat the prompt
_SAMPLE_ROWS = 3


def _tables(conn: Any) -> list[str]:
    """Real user tables in name order (SQLite internal ``sqlite_*`` excluded)."""
    rows = conn.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )
    return [r[0] for r in rows]


def _primary_key(conn: Any, table: str) -> str | None:
    """The single-column primary key of ``table`` (``None`` if composite/absent).

    SQLite reports a FK's parent column as ``NULL`` when it implicitly references
    the parent's PK — this resolves that to the real column name."""
    for r in conn.execute(text(f'PRAGMA table_info("{table}")')):
        if r[5]:  # pk flag > 0
            return r[1]
    return None


def foreign_keys(engine: Engine) -> list[tuple[str, str, str, str]]:
    """``(child_table, child_col, parent_table, parent_col)`` for every FK.

    From ``PRAGMA foreign_key_list`` (authoritative — what SQLite actually
    enforces), de-duplicated and sorted for a stable prompt. The implicit-PK
    parent column is resolved to its real name."""
    out: list[tuple[str, str, str, str]] = []
    with engine.connect() as conn:
        for t in _tables(conn):
            for r in conn.execute(text(f'PRAGMA foreign_key_list("{t}")')):
                child_col, parent, parent_col = r[3], r[2], r[4]
                if parent_col is None:
                    parent_col = _primary_key(conn, parent) or "(pk)"
                out.append((t, child_col, parent, parent_col))
    return sorted(set(out))


def sample_rows(
    engine: Engine, *, n: int = _SAMPLE_ROWS, max_cell: int = _MAX_CELL
) -> dict[str, tuple[list[str], list[tuple[Any, ...]]]]:
    """A few rows per table — ``{table: (columns, rows)}`` — cells truncated.

    Shows the model the *shape* of real values (date formats, code spellings) that
    the DDL's types alone don't convey."""
    out: dict[str, tuple[list[str], list[tuple[Any, ...]]]] = {}
    with engine.connect() as conn:
        for t in _tables(conn):
            res = conn.execute(text(f'SELECT * FROM "{t}" LIMIT {n}'))
            cols = list(res.keys())
            rows = [tuple(_truncate(v, max_cell) for v in row) for row in res]
            out[t] = (cols, rows)
    return out


def _truncate(value: Any, max_cell: int) -> Any:
    s = str(value)
    return value if len(s) <= max_cell else s[:max_cell] + "…"


def enriched_schema(engine: Engine, *, fks: bool = True, samples: bool = True) -> str:
    """The naive DDL dump + (optionally) surfaced relationships + sample rows.

    A drop-in replacement for ``schema_text`` on the enriched A/B arm — same
    ``schema`` input the generator already renders, just richer. ``fks`` and
    ``samples`` toggle the two enrichment components independently so the A/B can
    isolate which one helps (surfaced join paths) and which hurts (sample rows can
    distract the generator into copying a literal)."""
    parts = [schema_text(engine)]
    if fks:
        rels = foreign_keys(engine)
        rel = (
            "\n".join(f"  {c}.{cc} -> {p}.{pc}" for c, cc, p, pc in rels)
            if rels
            else "  (none declared)"
        )
        parts.append("-- Foreign-key relationships (join paths):\n" + rel)
    if samples:
        samp_lines: list[str] = []
        for t, (cols, rows) in sample_rows(engine).items():
            samp_lines.append(f"  {t} ({', '.join(cols)}):")
            samp_lines += [f"    {row}" for row in rows]
        parts.append("-- Sample rows (value formats):\n" + "\n".join(samp_lines))
    return "\n\n".join(parts) + "\n"
