"""The version-controlled field-description cache + metadata-source selector (#140).

The LLM-summarized field descriptions are **precompute**: run once, offline, and
frozen to a diffable artifact under ``profiles/`` — treated with the same discipline
as ``prompts/`` (checked in, reviewed, keyed by db + column). The live pipeline only
*reads* this cache; it never calls a model at request time for metadata. So a run is
reproducible and — the load-bearing boundary (CLAUDE.md §4/§7) — these descriptions
are **content for the generate prompt only**; they are never read by ``guard.py`` or
``eval/compare.py``, which stay deterministic and data-independent.

This module also owns the **metadata-source selector**: given the *supplied* metadata
(human SME descriptions, if any) and the *profiling* cache, it produces the per-column
description text for each source — ``supplied`` (current behaviour), ``profiling``
(data-derived only), or ``fused`` (both, the paper's best). The selector is a pure
function so the harness and the demo fuse metadata identically (import-shared).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Repo-root artifact dir, a peer of ``prompts/`` and ``fixtures/``. One JSON file
# per db, so a profile refresh is a reviewable, per-db diff.
PROFILES_DIR = Path(__file__).resolve().parents[3] / "profiles"


class MetadataSource(StrEnum):
    """Which field-description source the schema render uses (the #140 A/B axis)."""

    SUPPLIED = "supplied"  # human/SME metadata only — the current behaviour
    PROFILING = "profiling"  # data-derived (profiled + LLM-summarized) only
    FUSED = "fused"  # supplied + profiling (the paper's best: 63.2 vs 61.2/59.6)


@dataclass(frozen=True)
class FieldDescription:
    """The offline LLM summary of one column: a ``short`` gloss and a ``long`` one.

    ``short`` feeds schema **linking** (#138 — kept terse so many fields fit); ``long``
    feeds SQL **generation** (the format/meaning detail). Either may be empty.
    """

    short: str = ""
    long: str = ""


def field_key(table: str, column: str) -> str:
    """The cache key for a column — casefolded so lookups are case-insensitive."""
    return f"{table.casefold()}.{column.casefold()}"


def profile_path(db_id: str, *, profiles_dir: Path = PROFILES_DIR) -> Path:
    """The artifact path for ``db_id`` (``profiles/<db_id>.json``)."""
    return profiles_dir / f"{db_id}.json"


def load_field_descriptions(
    db_id: str, *, profiles_dir: Path = PROFILES_DIR
) -> dict[str, FieldDescription]:
    """Load a db's cached field descriptions, keyed ``"table.column"`` (casefolded).

    Returns an empty mapping when no artifact exists — so a db without a profile
    simply behaves as ``supplied``-only, never an error (graceful degrade). The
    live pipeline calls this; it does no model work.
    """
    path = profile_path(db_id, profiles_dir=profiles_dir)
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {
        key: FieldDescription(short=entry.get("short", ""), long=entry.get("long", ""))
        for key, entry in data.get("fields", {}).items()
    }


def save_field_descriptions(
    db_id: str,
    descriptions: dict[str, FieldDescription],
    *,
    profiles_dir: Path = PROFILES_DIR,
    generated_by: str = "",
) -> Path:
    """Write a db's field descriptions to its artifact (sorted keys, diffable).

    The offline summarization precompute calls this; keys are sorted and the JSON
    is pretty-printed so a re-run produces a minimal, reviewable diff — the same
    version-control discipline as a prompt template.
    """
    profiles_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "db_id": db_id,
        "generated_by": generated_by,
        "fields": {
            key: {"short": d.short, "long": d.long}
            for key, d in sorted(descriptions.items())
        },
    }
    path = profile_path(db_id, profiles_dir=profiles_dir)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def select_descriptions(
    source: MetadataSource,
    *,
    supplied: dict[str, str] | None = None,
    profiling: dict[str, FieldDescription] | None = None,
    use_long: bool = True,
) -> dict[str, str]:
    """Merge supplied + profiling metadata into per-column text for ``source``.

    Pure and deterministic — the harness and the demo call it identically. Keys are
    ``"table.column"`` (casefolded). ``use_long`` picks the profiling ``long``
    description (SQL generation) vs the ``short`` one (schema linking, #138).

    - ``SUPPLIED`` → the supplied text only (empty dict ⇒ the current behaviour).
    - ``PROFILING`` → the profiling description only, replacing any supplied text.
    - ``FUSED`` → supplied first, then the profiling description appended when the
      two differ (the paper's best; supplied names the intent, profiling the format).
    """
    supplied = {_normalize(k): v for k, v in (supplied or {}).items() if v}
    prof = {
        k: (d.long if use_long else d.short)
        for k, d in (profiling or {}).items()
        if (d.long if use_long else d.short)
    }

    if source is MetadataSource.SUPPLIED:
        return dict(supplied)
    if source is MetadataSource.PROFILING:
        return dict(prof)
    # FUSED: union of keys; combine where both are present and differ.
    merged: dict[str, str] = {}
    for key in supplied.keys() | prof.keys():
        s, p = supplied.get(key, ""), prof.get(key, "")
        if s and p and s.strip() != p.strip():
            merged[key] = f"{s} {p}"
        else:
            merged[key] = s or p
    return merged


def _normalize(key: str) -> str:
    """Casefold a ``"table.column"`` key so supplied and profiling keys line up."""
    return key.casefold()


def active_metadata_source() -> MetadataSource:
    """The metadata source named by ``METADATA_SOURCE``, else ``SUPPLIED``.

    Mirrors how ``MODEL`` / ``RUN_CONFIG`` are read (``run_config``): a blank or
    unrecognized value falls back to the default — ``SUPPLIED``, i.e. the current
    behaviour — so a clean checkout with no profiling artifact is unchanged, and a
    typo is a no-op rather than a crashed run.
    """
    name = os.environ.get("METADATA_SOURCE", "").strip().lower()
    try:
        return MetadataSource(name)
    except ValueError:
        return MetadataSource.SUPPLIED


def resolve_column_descriptions(
    db_id: str,
    source: MetadataSource | None = None,
    *,
    supplied: dict[str, str] | None = None,
    profiles_dir: Path = PROFILES_DIR,
    use_long: bool = True,
) -> dict[str, str]:
    """The per-column description dict for ``build_schema_index``, for one source.

    The single call the harness/demo make to turn a metadata *source* into the
    ``column_descriptions=`` map: it loads the profiling cache (empty if the db has
    no artifact) and merges it with ``supplied`` via :func:`select_descriptions`.
    ``source`` defaults to :func:`active_metadata_source` (the ``METADATA_SOURCE``
    env axis), so harness and demo resolve metadata identically (import-shared).
    """
    source = source if source is not None else active_metadata_source()
    profiling = load_field_descriptions(db_id, profiles_dir=profiles_dir)
    return select_descriptions(
        source, supplied=supplied, profiling=profiling, use_long=use_long
    )
