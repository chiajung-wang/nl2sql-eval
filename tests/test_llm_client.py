"""The LLM provider boundary (Step 7, issue #51) — offline.

The pipeline depends only on the ``LLMClient`` protocol; production backs it with
``LiteLLMClient`` (LiteLLM under the hood). These tests prove the adapter without
a network or key by monkeypatching ``litellm.completion``: the model string is
passed through untouched (so the *backend* is chosen purely by the identifier —
``anthropic/...`` direct, ``openrouter/...`` aggregated), and LiteLLM's
OpenAI-shaped response is normalized to ``LLMResponse`` with provider-agnostic
token counts. ``cost_usd`` then prices a provider-prefixed id off the bare-model
table.
"""

from __future__ import annotations

from types import SimpleNamespace

from eval.cost import cost_usd
from nl2sql.llm import LiteLLMClient, LLMResponse, default_client


def _fake_litellm_response(text: str, prompt_tokens: int, completion_tokens: int):
    """An OpenAI-shaped completion, the way LiteLLM returns it."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        ),
    )


def test_default_client_is_litellm_backed():
    assert isinstance(default_client(), LiteLLMClient)


def test_complete_passes_model_through_and_normalizes_response(monkeypatch):
    captured: dict = {}

    def fake_completion(*, model, messages, max_tokens, **kwargs):
        captured["model"] = model
        captured["prompt"] = messages[0]["content"]
        captured["max_tokens"] = max_tokens
        return _fake_litellm_response(
            "SELECT 1;", prompt_tokens=12, completion_tokens=3
        )

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)

    resp = LiteLLMClient().complete(
        "the prompt", model="anthropic/claude-sonnet-4-6", max_tokens=256
    )

    # Model identifier reaches LiteLLM untouched — the backend is the model string.
    assert captured["model"] == "anthropic/claude-sonnet-4-6"
    assert captured["prompt"] == "the prompt"
    assert captured["max_tokens"] == 256
    # OpenAI-shaped response normalized to the provider-agnostic LLMResponse, with
    # prompt/completion tokens mapped to input/output.
    assert isinstance(resp, LLMResponse)
    assert resp.text == "SELECT 1;"
    assert resp.input_tokens == 12
    assert resp.output_tokens == 3


def test_complete_routes_openrouter_identifier_unchanged(monkeypatch):
    seen: dict = {}

    def fake_completion(*, model, messages, max_tokens, **kwargs):
        seen["model"] = model
        return _fake_litellm_response("SELECT 2;", 1, 1)

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)

    LiteLLMClient().complete(
        "q", model="openrouter/anthropic/claude-sonnet-4", max_tokens=8
    )

    # OpenRouter is just another backend behind the same boundary — the aggregator
    # identifier is forwarded verbatim, no provider branching in our code.
    assert seen["model"] == "openrouter/anthropic/claude-sonnet-4"


def test_complete_tolerates_missing_usage(monkeypatch):
    def fake_completion(*, model, messages, max_tokens, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 3;"))],
            usage=None,
        )

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)

    resp = LiteLLMClient().complete(
        "q", model="anthropic/claude-sonnet-4-6", max_tokens=8
    )
    assert resp.text == "SELECT 3;"
    assert resp.input_tokens is None and resp.output_tokens is None


def test_cost_usd_prices_provider_prefixed_identifier():
    # The dated price table is keyed by the bare model; a LiteLLM provider prefix
    # is normalized to the last path segment so direct-Anthropic ids still price.
    bare = cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
    prefixed = cost_usd("anthropic/claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert prefixed == bare == 18.0  # 3.0 input + 15.0 output per 1M


def test_cost_usd_unknown_model_is_none():
    assert cost_usd("openrouter/some/unpriced-model", 100, 100) is None
