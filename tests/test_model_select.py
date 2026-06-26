"""The MODEL env override resolver — default pinned, override explicit, recorded.

The contract Step-11 #117 relies on: ``DEFAULT_MODEL`` is the canonical default
(unset env → unchanged behaviour, so a clean checkout reproduces the baseline);
``MODEL`` is an explicit override; a blank value is a no-op.
"""

from __future__ import annotations

from eval.model_select import model_id
from nl2sql.pipeline.generate import DEFAULT_MODEL


def test_unset_falls_back_to_pinned_default(monkeypatch):
    monkeypatch.delenv("MODEL", raising=False)
    assert model_id() == DEFAULT_MODEL


def test_model_env_overrides(monkeypatch):
    monkeypatch.setenv("MODEL", "openrouter/google/gemini-3-flash-preview")
    assert model_id() == "openrouter/google/gemini-3-flash-preview"


def test_blank_model_is_a_no_op(monkeypatch):
    monkeypatch.setenv("MODEL", "   ")
    assert model_id() == DEFAULT_MODEL
