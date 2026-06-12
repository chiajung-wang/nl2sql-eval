"""Token → USD pricing for the twin-metric cost accounting (Step 5, issue #43).

Self-correction is never free: pass@k spends extra generate calls, so the harness
reports the pass@1→pass@k accuracy lift *against* its added cost and latency. This
module turns the token counts captured on each run into a dollar figure.

Prices are a small, **dated** table — USD per 1M tokens, from the Claude API model
table (cached 2026-06-04). Because every reported cost in ``RESULTS.md`` is logged
alongside the token totals that produced it (CLAUDE.md §6), a later price revision
re-prices future runs without silently rewriting past ones. ``cost_usd`` returns
``None`` for an unpriced model rather than guessing, so an unknown model surfaces
as "cost unavailable" instead of a wrong number. The cross-provider cost table is
Step 7 (PRD); this is the single-model accounting that makes pass@k legible now.
"""

from __future__ import annotations

from dataclasses import dataclass

TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M input / output tokens for one model."""

    input_per_mtok: float
    output_per_mtok: float


# USD per 1M tokens. Source: Claude API model table (cached 2026-06-04). Update
# here when prices change; never hardcode a per-token rate at a call site.
PRICES: dict[str, ModelPrice] = {
    "claude-sonnet-4-6": ModelPrice(3.0, 15.0),
    "claude-haiku-4-5": ModelPrice(1.0, 5.0),
    "claude-opus-4-8": ModelPrice(5.0, 25.0),
    "claude-opus-4-7": ModelPrice(5.0, 25.0),
    "claude-opus-4-6": ModelPrice(5.0, 25.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD cost for ``input_tokens``/``output_tokens`` on ``model``.

    Returns ``None`` for a model not in :data:`PRICES` — the caller renders that
    as "unavailable" rather than reporting a fabricated cost.
    """
    price = PRICES.get(model)
    if price is None:
        return None
    return (
        input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok
    ) / TOKENS_PER_MILLION
