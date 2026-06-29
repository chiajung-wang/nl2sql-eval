"""The prompt registry: version pinning, fingerprinting, and clean-diff structure.

Step 9 (issue #57) externalizes prompts as version-controlled Jinja templates
structured for clean CI diffs: a shared static scaffold (``generate/_base.jinja``)
plus thin version files that ``{% extends %}`` it. These tests lock the two
guarantees prompt-CI relies on:

1. The active version refactor is **byte-identical** to the prior single-file v3
   (the pass@1-invariance claim) — moving the scaffold into a partial changed no
   rendered bytes.
2. The **fingerprint** covers the scaffold the active template pulls in, so a
   change to either the version file or the shared scaffold moves it.
"""

from __future__ import annotations

import subprocess
import sys

from nl2sql import prompts
from nl2sql.prompts import (
    GENERATE_TEMPLATE,
    PROMPT_VERSION,
    prompt_fingerprint,
    prompt_version,
    render,
)

# The exact bytes the single-file v3 produced before the scaffold was extracted
# into _base.jinja — the byte-identity anchor for the refactor.
_GOLDEN_NO_CORRECTION = (
    "\nYou are an expert data analyst who writes SQLite queries.\n\n"
    "Given the database schema and a question, write a single SQL query that "
    "answers\nthe question.\n\nRules:\n"
    "- Return ONLY the SQL query — no prose, no explanation, no markdown code "
    "fences.\n"
    "- Use only the tables and columns defined in the schema below.\n"
    "- Use SQLite syntax.\n"
    "- The query must be read-only: a single SELECT statement.\n"
    "- Prefer explicit column lists over SELECT *.\n\n"
    "Database schema (SQLite):\nSCH\n\nQuestion:\nq\n"
)


def _render(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "schema": "SCH",
        "question": "q",
        "dialect": "SQLite",
        "evidence": "",
        "correction": None,
    }
    kwargs.update(overrides)
    return render(GENERATE_TEMPLATE, **kwargs)


def test_active_template_is_byte_identical_to_prior_single_file_v3():
    # Extracting the scaffold into _base.jinja must not change a single byte of
    # the rendered prompt — otherwise the pass@1-invariance claim is false.
    assert _render() == _GOLDEN_NO_CORRECTION


def test_v4_adds_precision_rules_and_generic_examples_without_touching_v3():
    # v4 (#113) overrides only the rules block: output-precision rules + generic
    # worked examples. The examples must be generic (no eval-slice leakage), and
    # v3 must stay byte-identical (v4 doesn't modify the shared scaffold).
    v4 = render(
        "generate/v4.jinja",
        schema="SCH",
        question="q",
        dialect="SQLite",
        evidence="",
        correction=None,
    )
    assert "no extra columns" in v4
    assert "distinct / unique / different" in v4
    assert "Worked examples" in v4
    # generic example tables, not BIRD slice tables
    assert "SELECT DISTINCT city FROM customers" in v4
    # the scaffold still frames the real task after the examples
    assert "Database schema (SQLite):" in v4 and v4.rstrip().endswith("q")
    # v3 unchanged by v4's existence
    assert _render() == _GOLDEN_NO_CORRECTION


def test_correction_block_renders_through_the_shared_scaffold():
    out = _render(correction={"sql": "BAD", "error": "ERR"})
    assert "Your previous attempt failed." in out
    assert "BAD" in out and "ERR" in out
    # ...and the no-correction render omits it entirely (pass@1 prompt unchanged).
    assert "previous attempt" not in _render().lower()


def test_evidence_included_only_when_present():
    assert "External knowledge" in _render(evidence="rate = a / b")
    assert "External knowledge" not in _render()


def test_prompt_version_is_surfaced_and_matches_active_template():
    # The identifier RESULTS.md rows and CI pin; it names the active template.
    assert prompt_version() == PROMPT_VERSION == "generate/v3"
    assert PROMPT_VERSION.replace("generate/", "") in GENERATE_TEMPLATE


def test_fingerprint_is_stable_and_prefixed():
    fp = prompt_fingerprint()
    assert fp.startswith("sha256:")
    assert fp == prompt_fingerprint()  # deterministic


def test_fingerprint_covers_the_shared_scaffold_partial():
    # A change to the partial the active template extends must move the
    # fingerprint — that is the whole point of walking referenced templates.
    base = prompt_fingerprint()
    src = prompts.env().loader.get_source(prompts.env(), "generate/_base.jinja")[0]
    assert src  # sanity: the scaffold is a real referenced partial
    # The active version file references the scaffold, so both contribute bytes.
    refs = dict(prompts._referenced_sources(GENERATE_TEMPLATE, set()))
    assert "generate/_base.jinja" in refs
    assert base == prompt_fingerprint()  # idempotent


def test_block_override_changes_only_its_block_clean_diff():
    # The clean-diff property: a version that overrides one block (here, a v4-style
    # rules edit) changes only that block's bytes; the surrounding scaffold — the
    # intro, schema, question framing — is identical to the active prompt.
    edited = (
        prompts.env()
        .from_string(
            '{% extends "generate/_base.jinja" %}'
            "{% block rules %}- Return ONLY a single read-only SELECT.{% endblock %}"
        )
        .render(
            schema="SCH", question="q", dialect="SQLite", evidence="", correction=None
        )
    )
    active = _render()
    assert "- Return ONLY a single read-only SELECT." in edited
    # Everything outside the rules block is untouched.
    assert active.split("Rules:")[0] == edited.split("Rules:")[0]
    assert active.split("Database schema")[1] == edited.split("Database schema")[1]


def test_module_cli_prints_version_and_fingerprint():
    version = subprocess.run(
        [sys.executable, "-m", "nl2sql.prompts", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert version.stdout.strip() == PROMPT_VERSION
    fingerprint = subprocess.run(
        [sys.executable, "-m", "nl2sql.prompts", "--fingerprint"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert fingerprint.stdout.strip() == prompt_fingerprint()
