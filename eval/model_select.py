"""Resolve the generator model for an eval run — ``MODEL`` env over the named config.

The canonical default lives in the named-config registry (``run_config``, #132) so
a clean checkout reproduces the committed baseline. ``MODEL`` is an explicit,
opt-in override for experiments (baselining/diagnosing a different generator) —
mirroring how ``RETRY_BUDGET`` already works — and still wins over the selected
config. ``RUN_CONFIG`` selects a *named bundle* (e.g. ``accuracy``) so a banked
result is one switch, not a hand-assembled pair of env vars. Either way the
resolved model is **recorded**: every runner writes it into its ``RESULTS.md``
row, so a number can never silently depend on an untracked ``.env``.

**Adopting** a new default permanently is a *committed* registry change (the
``DEFAULT_CONFIG``), not a ``.env`` edit — this resolver is for experiments.
"""

from __future__ import annotations

import os

from nl2sql.run_config import active_config


def model_id() -> str:
    """The generator model: the ``MODEL`` env override, else the active config's.

    Precedence: an explicit ``MODEL`` wins; otherwise the ``RUN_CONFIG`` bundle (the
    default ``list-priced`` when unset). A blank/whitespace ``MODEL`` falls through
    to the config so an empty entry in ``.env`` is a no-op rather than an error."""
    return os.environ.get("MODEL", "").strip() or active_config().model
