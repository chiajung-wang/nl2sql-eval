"""Offline, cached LLM summarization of column profiles (Step 12, #140).

The LLM half of the paper's pipeline (arXiv:2505.19988v2 §2.1), and the one part
that calls a model — so it is **precompute**, not a pipeline stage: run once,
offline, and freeze the result to the version-controlled cache
(:mod:`nl2sql.profiling.cache`). The live pipeline reads that cache and never
summarizes at request time.

Given a column's mechanical English profile (:mod:`nl2sql.profiling.render`) and its
names, the model produces a **short** gloss (schema linking, #138) and a **long**
description (SQL generation). The prompt is externalized (``prompts/profile_summary``,
CLAUDE.md §4); the model reply is parsed as a small JSON object. A parse failure
degrades to the deterministic English as the ``long`` description — still valid
profiling metadata, just not model-polished — so the precompute never yields nothing.

The ``LLMClient`` seam is injected (real client in the CLI, a fake in tests), so the
summarization logic is fully offline-testable without a key; the live refresh over a
real db is deferred (gated on an authorized key/spend — ``defer-api-key-verification``).
"""

from __future__ import annotations

import argparse
import json
import logging

from nl2sql import prompts
from nl2sql.llm.client import LLMClient
from nl2sql.profiling.cache import (
    FieldDescription,
    field_key,
    save_field_descriptions,
)
from nl2sql.profiling.profiler import ColumnProfile, DbProfile, profile_db
from nl2sql.profiling.render import render_column_english

logger = logging.getLogger(__name__)

SUMMARY_TEMPLATE = "profile_summary/v1.jinja"
# Generous ceiling: a short + long JSON summary is small, but a reasoning model may
# think first (the #124 lesson). Never near a real cap for this task.
DEFAULT_SUMMARY_MAX_TOKENS = 1024


def _parse_summary(text: str, *, fallback_long: str) -> FieldDescription:
    """Parse the model's JSON reply into a :class:`FieldDescription`.

    Tolerant: strips a leading/trailing markdown fence, then extracts the outermost
    ``{...}`` before ``json.loads`` (a reasoning model may wrap the object in prose).
    On any failure, degrades to ``fallback_long`` (the deterministic English) as the
    ``long`` description — so a malformed reply still yields usable metadata.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        # Drop a leading language tag like ``json`` left by the fence strip.
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(stripped[start : end + 1])
            return FieldDescription(
                short=str(obj.get("short", "")).strip(),
                long=str(obj.get("long", "")).strip() or fallback_long,
            )
        except (json.JSONDecodeError, AttributeError):
            pass
    logger.warning("profile summary did not parse as JSON; using deterministic English")
    return FieldDescription(short="", long=fallback_long)


def summarize_column(
    client: LLMClient,
    db_id: str,
    profile: ColumnProfile,
    *,
    model: str,
    max_tokens: int = DEFAULT_SUMMARY_MAX_TOKENS,
) -> FieldDescription:
    """Summarize one column's profile into short + long descriptions (one LLM call)."""
    english = render_column_english(profile)
    prompt = prompts.render(
        SUMMARY_TEMPLATE,
        db_id=db_id,
        table_name=profile.table,
        column_name=profile.name,
        declared_type=profile.declared_type or "?",
        profile_english=english,
    )
    reply = client.complete(prompt, model=model, max_tokens=max_tokens)
    return _parse_summary(reply.text, fallback_long=english)


def summarize_db(
    client: LLMClient,
    db_profile: DbProfile,
    *,
    model: str,
    max_tokens: int = DEFAULT_SUMMARY_MAX_TOKENS,
) -> dict[str, FieldDescription]:
    """Summarize every column of a db profile, keyed ``"table.column"`` (casefolded)."""
    out: dict[str, FieldDescription] = {}
    for table in db_profile.tables:
        for col in table.columns:
            out[field_key(col.table, col.name)] = summarize_column(
                client, db_profile.db_id, col, model=model, max_tokens=max_tokens
            )
    return out


def _main(argv: list[str] | None = None) -> int:
    """CLI: profile a db and write its cached field descriptions (deferred).

    Offline-first: the profiler and renderer run with no key; only a run *with*
    ``--model`` calls a model. Without one, ``--dry-run`` prints the mechanical
    English so the precompute is inspectable before any spend.
    """
    parser = argparse.ArgumentParser(
        description="Profile a db and summarize its fields."
    )
    parser.add_argument("--db-url", required=True, help="SQLAlchemy URL to profile")
    parser.add_argument("--db-id", required=True, help="db identity (artifact key)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the deterministic English only; no model call, no write",
    )
    parser.add_argument("--model", default="", help="model for --summarize")
    args = parser.parse_args(argv)

    # Load .env so the provider key is available (mirrors the eval entrypoints); a
    # dry-run needs no key, so a missing .env is harmless there.
    from dotenv import load_dotenv

    load_dotenv()

    from sqlalchemy import create_engine

    engine = create_engine(args.db_url, future=True)
    db_profile = profile_db(engine, args.db_id)

    if args.dry_run or not args.model:
        for table in db_profile.tables:
            for col in table.columns:
                print(f"[{col.table}.{col.name}] {render_column_english(col)}")
        return 0

    from nl2sql.llm.client import default_client

    descriptions = summarize_db(default_client(), db_profile, model=args.model)
    path = save_field_descriptions(
        args.db_id, descriptions, generated_by=f"profile_summary/v1 · {args.model}"
    )
    print(f"wrote {len(descriptions)} field descriptions to {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
