"""Resolve the generator model for an eval run — the ``MODEL`` env override.

The canonical default lives **pinned in code** (``generate.DEFAULT_MODEL``) so a
clean checkout reproduces the committed baseline. ``MODEL`` is an explicit,
opt-in override for experiments (baselining/diagnosing a different generator) —
mirroring how ``RETRY_BUDGET`` already works. The override is always **recorded**:
every runner writes the resolved model into its ``RESULTS.md`` row, so a number
can never silently depend on an untracked ``.env``.

**Adopting** a new default permanently is a *committed* ``DEFAULT_MODEL`` change,
not a ``.env`` edit — this resolver is for experiments, not for changing the pin.
"""

from __future__ import annotations

import os

from nl2sql.pipeline.generate import DEFAULT_MODEL


def model_id() -> str:
    """The generator model: the ``MODEL`` env override, else the pinned default.

    A blank/whitespace ``MODEL`` falls back to ``DEFAULT_MODEL`` so an empty entry
    in ``.env`` is a no-op rather than an error."""
    return os.environ.get("MODEL", "").strip() or DEFAULT_MODEL
