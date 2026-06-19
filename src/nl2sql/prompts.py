"""Prompt registry — the single source of truth for externalized templates.

Prompts live in the repo-root ``prompts/`` directory as version-controlled
Jinja templates (CI diffs that dir; never inline prompt strings in Python —
CLAUDE.md §4). This module centralizes the four things every other module and
the prompt-CI workflow need:

1. **Where** the templates live (``PROMPTS_DIR``) and the shared Jinja
   environment that renders them (``env`` / :func:`render`).
2. The **active prompt version** (``PROMPT_VERSION``) pinned into every
   ``RESULTS.md`` row and CI run, so a number always traces to the prompt that
   produced it (CLAUDE.md §6).
3. A content **fingerprint** of the active template *and the partials it pulls
   in* (:func:`prompt_fingerprint`), so prompt-CI can pin the exact bytes — a
   version string can lie if someone edits in place; the fingerprint cannot.

Templates are structured for **clean CI diffs** (Step 9): the static scaffold
lives once in ``generate/_base.jinja`` and each version file is a thin
``{% extends %}`` that overrides only the blocks it changes. A prompt edit then
shows as a tight diff in one block, not a 35-line whole-file rewrite — and the
shared scaffold "stays put" across versions.

Run as a module to surface the active prompt to CI/shell::

    python -m nl2sql.prompts --version       # -> generate/v3
    python -m nl2sql.prompts --fingerprint   # -> sha256:...
"""

from __future__ import annotations

import argparse
import hashlib
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, meta

# The repo-root prompts/ dir (CI diffs it): two parents up from
# src/nl2sql/prompts.py.
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# The active generate template and the version string pinned into RESULTS.md and
# CI. Bump *both* together when the active template changes (a new vN.jinja).
GENERATE_TEMPLATE = "generate/v3.jinja"
PROMPT_VERSION = "generate/v3"


@lru_cache(maxsize=1)
def env() -> Environment:
    """The shared Jinja environment for ``prompts/`` (one per process).

    ``StrictUndefined`` turns a missing template variable into an error instead
    of a silent empty string — a prompt that silently drops the schema would
    corrupt every downstream number. ``keep_trailing_newline`` preserves the
    template's final newline so rendered prompts are byte-stable.
    """
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render(template_name: str, /, **variables: object) -> str:
    """Render an externalized template by name, e.g. ``"generate/v3.jinja"``."""
    return env().get_template(template_name).render(**variables)


def prompt_version() -> str:
    """The active prompt-version identifier pinned into RESULTS.md and CI."""
    return PROMPT_VERSION


def _referenced_sources(template_name: str, seen: set[str]) -> list[tuple[str, str]]:
    """Collect ``(name, source)`` for a template and everything it pulls in.

    Walks Jinja ``{% extends %}``/``{% include %}``/``{% import %}`` references
    recursively so the fingerprint covers the **whole rendered prompt** — the
    shared ``_base.jinja`` scaffold a version file extends, not just the thin
    version file's own bytes.
    """
    if template_name in seen:
        return []
    seen.add(template_name)
    source, _, _ = env().loader.get_source(env(), template_name)
    collected = [(template_name, source)]
    for ref in meta.find_referenced_templates(env().parse(source)):
        if ref is not None:  # None = a dynamically-named reference; skip
            collected.extend(_referenced_sources(ref, seen))
    return collected


def prompt_fingerprint(template_name: str | None = None) -> str:
    """A stable ``sha256:`` digest over a template and its referenced partials.

    Byte- and comment-sensitive on purpose: any edit to the active prompt — its
    scaffold, a rule, the correction wording — changes the fingerprint. That is
    what lets prompt-CI pin *exactly* which prompt produced a number, even if a
    version string is left stale. Defaults to the active generate template.
    """
    template_name = template_name or GENERATE_TEMPLATE
    digest = hashlib.sha256()
    for name, source in sorted(_referenced_sources(template_name, set())):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(source.encode())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Surface the active prompt version / fingerprint to CI."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--version",
        action="store_true",
        help="print the active prompt-version identifier (default)",
    )
    group.add_argument(
        "--fingerprint",
        action="store_true",
        help="print the content fingerprint instead of the version string",
    )
    args = parser.parse_args(argv)
    print(prompt_fingerprint() if args.fingerprint else prompt_version())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
