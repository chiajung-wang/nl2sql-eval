"""Named run configs (#132) — selection, precedence, and the byte-identical default.

Offline and deterministic: only env resolution, no model calls. The contract that
matters is precedence (an explicit ``MODEL`` / ``MAX_TOKENS`` still wins over the
named bundle) and that an unset ``RUN_CONFIG`` reproduces the prior pinned default.
"""

from __future__ import annotations

import pytest

from nl2sql.run_config import (
    ACCURACY,
    CONFIGS,
    DEFAULT_CONFIG,
    LIST_PRICED,
    active_config,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts clean — no inherited RUN_CONFIG/MODEL/MAX_TOKENS."""
    for var in ("RUN_CONFIG", "MODEL", "MAX_TOKENS"):
        monkeypatch.delenv(var, raising=False)


# --- the registry -----------------------------------------------------------


def test_default_config_is_list_priced_and_unchanged():
    # The default must be the prior pinned baseline (a direct, list-priced model)
    # so a clean checkout reproduces the committed numbers and cost accounting.
    assert DEFAULT_CONFIG is LIST_PRICED
    assert LIST_PRICED.model == "anthropic/claude-sonnet-4-6"
    assert LIST_PRICED.max_tokens == 4096


def test_accuracy_config_bundles_gemini_and_the_reasoning_budget():
    assert ACCURACY.model == "openrouter/google/gemini-3.5-flash"
    assert ACCURACY.max_tokens == 4096  # reasoning model needs the headroom (#124)


def test_configs_registry_is_keyed_by_name():
    assert CONFIGS == {"list-priced": LIST_PRICED, "accuracy": ACCURACY}


# --- selection --------------------------------------------------------------


def test_active_config_defaults_when_unset():
    assert active_config() is DEFAULT_CONFIG


def test_active_config_selects_by_name(monkeypatch):
    monkeypatch.setenv("RUN_CONFIG", "accuracy")
    assert active_config() is ACCURACY


@pytest.mark.parametrize("value", ["", "   ", "nonsense", "Accuracy"])
def test_active_config_falls_back_on_blank_or_unknown(monkeypatch, value):
    # Blank, whitespace, a typo, or wrong case → the default, never a crash
    # (mirrors how MODEL/MAX_TOKENS degrade gracefully).
    monkeypatch.setenv("RUN_CONFIG", value)
    assert active_config() is DEFAULT_CONFIG


# --- precedence into the resolvers ------------------------------------------


def test_model_id_uses_active_config_then_explicit_model_wins(monkeypatch):
    from eval.model_select import model_id

    # Default → list-priced model.
    assert model_id() == "anthropic/claude-sonnet-4-6"
    # RUN_CONFIG selects the bundle.
    monkeypatch.setenv("RUN_CONFIG", "accuracy")
    assert model_id() == "openrouter/google/gemini-3.5-flash"
    # An explicit MODEL still wins over the bundle.
    monkeypatch.setenv("MODEL", "anthropic/claude-haiku-4-5")
    assert model_id() == "anthropic/claude-haiku-4-5"


def test_max_tokens_uses_active_config_then_explicit_env_wins(monkeypatch):
    from nl2sql.pipeline.generate import _max_tokens

    # Default → list-priced budget (4096), byte-identical to before.
    assert _max_tokens() == 4096
    # An explicit MAX_TOKENS still wins.
    monkeypatch.setenv("MAX_TOKENS", "1024")
    assert _max_tokens() == 1024
    # A blank/garbage MAX_TOKENS falls back to the active config, not a crash.
    monkeypatch.setenv("MAX_TOKENS", "  ")
    assert _max_tokens() == 4096


def test_pinned_defaults_match_the_config():
    # The generate-stage constants are sourced from the registry, so they can't
    # drift from the default config.
    from nl2sql.pipeline.generate import DEFAULT_MAX_TOKENS, DEFAULT_MODEL

    assert DEFAULT_MODEL == DEFAULT_CONFIG.model
    assert DEFAULT_MAX_TOKENS == DEFAULT_CONFIG.max_tokens
