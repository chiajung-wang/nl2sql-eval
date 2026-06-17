"""Cross-provider table harness (Step 7, issue #52) — offline.

The live run needs provider keys; this exercises the pure pieces with synthetic
``BatchReport``s: model-list parsing, per-row client/routing selection, the
cost-basis split (OpenRouter's reported cost vs the dated list table), pass@1
derivation, and table rendering. No network, no key.
"""

from __future__ import annotations

import eval.eval_cross_provider as xp
from eval.eval_cross_provider import (
    OPENROUTER_ROUTING_PIN,
    PROVIDER_ERROR_PREFIX,
    ProviderRow,
    cost_basis,
    cross_provider_models,
    make_client,
    make_factory,
    provider_errors,
    provider_row,
    render_table,
    results_row,
    row_cost,
)
from eval.harness import Case
from eval.metrics import BatchReport, CaseResult
from nl2sql.llm import LiteLLMClient
from nl2sql.pipeline.state import TerminalState


def _case(
    cid: str,
    *,
    correct: bool,
    attempts: int = 1,
    inp: int = 0,
    out: int = 0,
    provider_cost: float | None = None,
    latency_ms: float = 0.0,
    note: str | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=cid,
        db_id="bird",
        terminal_state=TerminalState.SUCCESS if correct else TerminalState.WRONG_ANSWER,
        correct=correct,
        attempts=attempts,
        input_tokens=inp,
        output_tokens=out,
        latency_ms=latency_ms,
        provider_cost_usd=provider_cost,
        note=note,
    )


# --- model-list parsing -----------------------------------------------------


def test_models_default_to_single_model_when_unset(monkeypatch):
    monkeypatch.delenv("CROSS_PROVIDER_MODELS", raising=False)
    from nl2sql.pipeline.generate import DEFAULT_MODEL

    assert cross_provider_models() == [DEFAULT_MODEL]


def test_models_parse_comma_list_and_trim(monkeypatch):
    monkeypatch.setenv(
        "CROSS_PROVIDER_MODELS",
        " openrouter/anthropic/claude-sonnet-4 , openrouter/openai/gpt-4o-mini ,",
    )
    assert cross_provider_models() == [
        "openrouter/anthropic/claude-sonnet-4",
        "openrouter/openai/gpt-4o-mini",
    ]


# --- per-row client / routing pin -------------------------------------------


def test_openrouter_model_pins_provider_routing():
    client = make_client("openrouter/anthropic/claude-sonnet-4")
    assert isinstance(client, LiteLLMClient)
    # The frozen-slice repeatability pin reaches LiteLLM (PRD §9).
    assert client._extra_params == OPENROUTER_ROUTING_PIN
    assert OPENROUTER_ROUTING_PIN["provider"]["allow_fallbacks"] is False


def test_direct_model_uses_default_client():
    assert make_client("anthropic/claude-sonnet-4-6") is None


def test_cost_basis_split():
    assert cost_basis("openrouter/openai/gpt-4o-mini") == "openrouter"
    assert cost_basis("anthropic/claude-sonnet-4-6") == "direct-list"


# --- cost basis -------------------------------------------------------------


def test_row_cost_openrouter_uses_provider_reported_sum():
    report = BatchReport(
        (
            _case("a", correct=True, provider_cost=0.0012),
            _case("b", correct=False, provider_cost=0.0008),
        )
    )
    # OpenRouter's own reported price — not the dated list table.
    assert row_cost("openrouter/openai/gpt-4o-mini", report) == 0.0020


def test_row_cost_direct_uses_dated_list_table():
    # 1M input + 1M output on sonnet-4-6 = $3 + $15 = $18 from eval.cost.
    report = BatchReport((_case("a", correct=True, inp=1_000_000, out=1_000_000),))
    assert row_cost("anthropic/claude-sonnet-4-6", report) == 18.0


def test_row_cost_is_none_when_unavailable():
    # OpenRouter row but no provider cost surfaced → None (renders "n/a").
    report = BatchReport((_case("a", correct=True, provider_cost=None),))
    assert row_cost("openrouter/x/y", report) is None


# --- pass@1 derivation + rendering ------------------------------------------


def test_provider_row_derives_pass1_from_passk_first_attempts():
    # One first-shot success, one recovered-on-retry (pass@1 wrong, pass@k right),
    # one clean wrong. pass@k = 2/3, pass@1 = 1/3.
    passk = BatchReport(
        (
            _case("a", correct=True, attempts=1, provider_cost=0.001),
            _case("b", correct=True, attempts=2, provider_cost=0.002),
            _case("c", correct=False, attempts=1, provider_cost=0.001),
        )
    )
    row = provider_row("openrouter/anthropic/claude-sonnet-4", passk)
    assert (row.n_correct_k, row.total) == (2, 3)
    assert row.n_correct_1 == 1  # the retried-then-recovered run is pass@1 wrong
    assert row.cost_usd == 0.004  # provider-reported sum
    assert row.cost_basis == "openrouter"


def test_render_table_formats_cost_and_na():
    rows = [
        ProviderRow(
            model="openrouter/openai/gpt-4o-mini",
            total=40,
            n_correct_1=20,
            n_correct_k=22,
            cost_usd=0.0123,
            cost_basis="openrouter",
            mean_latency_ms=812.4,
        ),
        ProviderRow(
            model="openrouter/x/y",
            total=40,
            n_correct_1=18,
            n_correct_k=18,
            cost_usd=None,
            cost_basis="openrouter",
            mean_latency_ms=500.0,
        ),
    ]
    table = render_table(rows, k=3)
    assert "pass@1 | pass@3 | cost (USD) | cost basis" in table
    assert "provider errors" in table  # the resilience column
    assert "0.500 (20/40)" in table and "0.550 (22/40)" in table
    assert "$0.0123" in table
    assert "| n/a |" in table  # missing cost renders n/a, never a fabricated number


def test_results_row_points_at_best_model():
    rows = [
        ProviderRow("openrouter/a/m1", 40, 20, 22, 0.01, "openrouter", 800.0),
        ProviderRow("openrouter/a/m2", 40, 26, 28, 0.02, "openrouter", 900.0),
    ]
    row = results_row(rows, k=3, commit="abc1234")
    assert "| 7 |" in row and "best pass@1 0.650 (`openrouter/a/m2`)" in row
    assert "abc1234" in row


# --- resilience: a provider error must not abort the whole run ---------------


def test_provider_errors_counts_only_provider_failures():
    report = BatchReport(
        (
            _case("ok", correct=True),
            _case(
                "sql_err",
                correct=False,
                note="(sqlite3.OperationalError) no such table",
            ),
            _case(
                "rate",
                correct=False,
                note=f"{PROVIDER_ERROR_PREFIX} RateLimitError: 429",
            ),
        )
    )
    assert provider_errors(report) == 1
    # And it surfaces on the row so a depressed accuracy is read in context.
    assert provider_row("openrouter/a/m", report).provider_errors == 1


def test_guarded_runner_captures_provider_exception(monkeypatch):
    # A rate limit (or any provider/transport error) is caught per case and turned
    # into an errored RunState — the batch survives instead of the whole job dying.
    def boom(*args, **kwargs):
        raise RuntimeError("RateLimitError: 429 temporarily rate-limited upstream")

    monkeypatch.setattr(xp, "_schema", lambda db_id: "CREATE TABLE t (id INT);")
    monkeypatch.setattr(xp, "_engine", lambda db_id: None)
    monkeypatch.setattr(xp, "run_pipeline", boom)

    run_one = make_factory("openrouter/a/m", {})(3)
    case = Case(
        id="q1", question="q", db_id="bird", gold_sql="SELECT 1", gold_result={}
    )
    state = run_one(case)

    assert state.error is not None
    assert state.error.startswith(PROVIDER_ERROR_PREFIX)
    assert "RateLimitError" in state.error
    assert state.attempts == 1  # buckets as a single-shot error, not a crash
