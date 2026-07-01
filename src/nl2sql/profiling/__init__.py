"""Profiling-derived field metadata (Step 12, #140).

Source: Shkapenyuk et al., "Automatic Metadata Extraction for Text-to-SQL"
(arXiv:2505.19988v2, §2 / §2.1). Their central, surprising result: **profiling the
data beats human-supplied metadata** (MiniDev, no hints: profiling 61.2 vs supplied
59.6; fused best at 63.2), because cryptic schemas hide format and meaning the data
exposes — that ``CDSCode`` is a 14-char id, that ``Academic Year`` is ``'YYYY-YYYY'``,
that an undocumented column is JSON.

The pipeline here mirrors the paper, split by determinism boundary (CLAUDE.md §4):

1. :mod:`nl2sql.profiling.profiler` — a **deterministic** per-column profile
   (counts, NULL/non-NULL, distinct, value shape, top-k) over SQLAlchemy. No LLM.
2. :mod:`nl2sql.profiling.render` — a **mechanical** profile→English rendering. No
   LLM, so it is reproducible and offline-testable.
3. :mod:`nl2sql.profiling.summarize` — the **offline, cached** LLM summarization
   (short description for schema linking, long for SQL generation). Run once and
   frozen to a version-controlled artifact keyed by db+column; the live pipeline
   only *reads* the cache (:mod:`nl2sql.profiling.cache`). This is precompute, not
   a pipeline stage.

**Load-bearing boundary:** the LLM-summarized descriptions are *content for the
generate prompt only*. They must never reach ``guard.py`` or ``eval/compare.py`` —
those stay deterministic and data-independent, so scoring is untouched and a run is
reproducible.
"""

from __future__ import annotations

from nl2sql.profiling.cache import (
    FieldDescription,
    MetadataSource,
    active_metadata_source,
    load_field_descriptions,
    resolve_column_descriptions,
    save_field_descriptions,
    select_descriptions,
)
from nl2sql.profiling.profiler import (
    CharClass,
    ColumnProfile,
    DbProfile,
    TableProfile,
    profile_column,
    profile_db,
    profile_table,
)
from nl2sql.profiling.render import render_column_english, render_table_english

__all__ = [
    "CharClass",
    "ColumnProfile",
    "TableProfile",
    "DbProfile",
    "profile_column",
    "profile_table",
    "profile_db",
    "render_column_english",
    "render_table_english",
    "FieldDescription",
    "MetadataSource",
    "active_metadata_source",
    "load_field_descriptions",
    "save_field_descriptions",
    "select_descriptions",
    "resolve_column_descriptions",
]
