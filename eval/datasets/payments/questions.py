"""Loader for the verified payments question set (Issue 3).

The hand-authored ``questions.json`` is the trusted ground Step 3 validates the
harness against before pointing it at BIRD. This module is the import surface
the harness uses so callers never hardcode the JSON path. Gold answers are
verified against the Issue 2 seed (see ``questions.json`` ``_meta.verification``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

QUESTIONS_JSON = Path(__file__).parent / "questions.json"


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    return json.loads(QUESTIONS_JSON.read_text())


def load_questions() -> list[dict[str, Any]]:
    """Return the list of verified Q/A records (each with gold_sql + gold_result)."""
    return _load()["questions"]


def load_meta() -> dict[str, Any]:
    """Return the dataset provenance/format metadata block."""
    return _load()["_meta"]
