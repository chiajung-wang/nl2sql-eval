"""Named run configs — pick an *axis* (accuracy vs. list-priced cost accounting)
by name, not by reconstructing env vars from the README.

Step 11 (#132) banks the validated model swap. The accuracy lever — running the
generator as ``gemini-3.5-flash`` with a reasoning-model output budget — measured
the top dev pass@1 (0.520 strict / 0.580 BIRD, #124), **+0.10 over the sonnet
baseline**, and carries no slice-overfitting risk (the model was never tuned on
these questions). But the win lived only in README prose: a reader had to assemble
``MODEL=…`` + ``MAX_TOKENS=…`` by hand. This module makes each config a *named
bundle* the harness and the demo select the same way — the measurement apparatus
is the product (CLAUDE.md §1), so a banked result ships as a switch, not a
paragraph.

Why two configs rather than one repinned default:

- **list-priced** (the default) keeps the pinned ``anthropic/claude-sonnet-4-6`` —
  a *direct, list-priced* model, so ``eval.cost`` prices it dollar-for-dollar.
  Repinning to the OpenRouter gemini globally would make the project's default
  depend on a third-party aggregator and forfeit clean cost accounting
  (``cost_usd`` doesn't price OpenRouter models, #52). That objection (#117) still
  stands, so the default is unchanged.
- **accuracy** is the top-of-slice config — for when accuracy, not cost
  accounting, is the axis that matters.

**Precedence.** An explicit ``MODEL`` / ``MAX_TOKENS`` env var still wins over the
selected config (so existing per-knob overrides are untouched); the config fills
in only what an env var hasn't pinned. With **nothing** set, ``RUN_CONFIG`` is the
default (list-priced) and every resolved value equals the prior pinned default —
a clean checkout is byte-identical to before this module existed.

This module imports nothing from the pipeline, so ``generate`` can read its
defaults from here without an import cycle.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RunConfig:
    """A named bundle of the generator knobs that define a run's accuracy/cost axis.

    Deliberately only **model** and **max_tokens** — the two knobs that actually
    differ between the accuracy and cost axes. Two things a config might seem to
    want are kept *out* on purpose, to avoid a second source of truth:

    - **prompt version** is owned by the prompt registry (``nl2sql.prompts``), the
      single source of truth CI diffs (CLAUDE.md §4). Storing a version literal
      here would duplicate it and silently drift; both configs run the active
      template regardless, so the config has nothing to add.
    - **dialect** is a per-*dataset* input (SQLite on BIRD, PostgreSQL on the
      payments demo), resolved per run — it does not vary between the accuracy and
      list-priced axes, so it is not a property of the config.
    """

    name: str
    model: str
    max_tokens: int


# The direct, list-priced default — unchanged from the pinned baseline. Sonnet 4.x
# per CLAUDE.md §2; ``anthropic/`` is a direct provider key (priced by ``eval.cost``).
LIST_PRICED = RunConfig(
    name="list-priced",
    model="anthropic/claude-sonnet-4-6",
    max_tokens=4096,
)

# The top-of-slice accuracy config (#124). A *reasoning* model: it spends
# ~1000-1150 output tokens thinking before emitting SQL, so it needs the 4096
# budget — at the old 1024 cap it truncated mid-thought and looked broken.
ACCURACY = RunConfig(
    name="accuracy",
    model="openrouter/google/gemini-3.5-flash",
    max_tokens=4096,
)

CONFIGS: dict[str, RunConfig] = {c.name: c for c in (LIST_PRICED, ACCURACY)}

# The default when ``RUN_CONFIG`` is unset/blank/unknown — the pinned baseline, so
# a clean checkout reproduces the committed numbers.
DEFAULT_CONFIG = LIST_PRICED


def active_config() -> RunConfig:
    """The config named by ``RUN_CONFIG``, else :data:`DEFAULT_CONFIG`.

    A blank or unrecognized name falls back to the default rather than raising, so
    an empty ``.env`` entry or a typo is a no-op (mirrors how ``MODEL`` /
    ``MAX_TOKENS`` degrade gracefully) — never a crashed run.
    """
    name = os.environ.get("RUN_CONFIG", "").strip()
    return CONFIGS.get(name, DEFAULT_CONFIG)
