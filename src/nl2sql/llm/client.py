"""LLM provider boundary — one seam, many backends (via LiteLLM).

Step 7 (issue #51) replaces the direct single-provider Anthropic call with a
**LiteLLM** abstraction so the cross-provider cost/accuracy table (#52) becomes
trivial — and mirrors JKOPay's actual "LiteLLM Gateway" stack. LiteLLM is the
boundary; the *backend* is selectable behind it purely by the model identifier:

- ``anthropic/claude-...`` — a direct provider key (``ANTHROPIC_API_KEY``).
- ``openrouter/...`` — an aggregator reaching many models through one key
  (``OPENROUTER_API_KEY``). OpenRouter is a provider *behind* LiteLLM, not a
  replacement for it.

The pipeline depends only on the tiny ``LLMClient`` protocol below (a single
``complete`` call returning text + token usage), never on a vendor SDK. Tests
inject a fake ``LLMClient``; production uses ``LiteLLMClient``. The provider is
chosen by the ``model`` string the caller passes — no provider branching here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Per-request timeout (seconds) and retry budget, so a batch eval can't stall
# indefinitely on a hung connection: under provider congestion a stuck socket
# fails fast and LiteLLM retries on a fresh one rather than blocking the run.
REQUEST_TIMEOUT_S = 45.0
REQUEST_MAX_RETRIES = 8


@dataclass
class LLMResponse:
    """The provider-agnostic shape the pipeline consumes.

    ``text`` is the model's completion; the token counts are normalized across
    providers (LiteLLM's ``prompt_tokens``/``completion_tokens`` map to
    ``input_tokens``/``output_tokens``) so the harness can price a run's total
    cost identically regardless of backend. Counts are ``None`` when a provider
    omits usage.

    ``cost_usd`` is the **provider-reported** cost of this call, when LiteLLM
    surfaces one (e.g. via OpenRouter). It is the authentic cost basis for the
    cross-provider table (#52) — OpenRouter's own normalized/marked-up price, not
    the direct-list table in ``eval.cost`` — and ``None`` when no provider cost is
    available (then the caller falls back to the dated list table by model).
    """

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


@runtime_checkable
class LLMClient(Protocol):
    """The one seam the pipeline depends on: a single text completion.

    Deterministic from the pipeline's view — same prompt + model in, one
    ``LLMResponse`` out. Implemented by ``LiteLLMClient`` in production and by a
    fake in tests, so the generate/correct stages never import a vendor SDK.
    """

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LLMResponse: ...


class LiteLLMClient:
    """``LLMClient`` backed by LiteLLM — multi-provider via the model string.

    LiteLLM is imported lazily so importing this module (and the pipeline) needs
    neither the package warm nor any API key; the key is read from the
    environment by LiteLLM at call time, keyed to the provider in ``model``.
    """

    def __init__(
        self,
        *,
        timeout: float = REQUEST_TIMEOUT_S,
        max_retries: int = REQUEST_MAX_RETRIES,
        extra_params: dict[str, object] | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        # Extra keyword args forwarded verbatim to ``litellm.completion`` — the
        # hook for backend-specific routing without touching the seam. The
        # cross-provider run (#52) uses it to pin OpenRouter routing
        # (``provider={"allow_fallbacks": False, ...}``) so an ``openrouter/…`` row
        # can't silently switch backend mid-slice and break repeatability (PRD §9).
        self._extra_params = extra_params or {}

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LLMResponse:
        import litellm

        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            timeout=self._timeout,
            num_retries=self._max_retries,
            **self._extra_params,
        )
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        # LiteLLM stashes the computed/provider-returned cost here (USD); present
        # for OpenRouter and most backends, absent for some — then ``None``.
        hidden = getattr(response, "_hidden_params", None) or {}
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            cost_usd=hidden.get("response_cost"),
        )


def default_client() -> LLMClient:
    """The production client: LiteLLM, provider chosen by the model identifier."""
    return LiteLLMClient()
