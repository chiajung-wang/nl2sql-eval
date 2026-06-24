"""The demo's testable core: run one question, return a view of the *wrapper*.

Streamlit is hard to unit-test, so all the logic lives here as a pure function
over an injected engine + LLM client; ``app.py`` is a thin shell that renders the
returned :class:`DemoView`. This keeps the demo honest in two ways:

1. It calls the **import-shared** ``run_pipeline`` (never a fork) and the
   **harness's own** ``classify_terminal_state`` — the exact code the eval
   measures — so what the demo shows can't drift from the numbers.
2. The view exposes only the **presented (redacted) result** (``presented_*``),
   never the raw verified rows — the same two-exit discipline the harness scores
   upstream of (CLAUDE.md §3/§5). Raw PII cannot reach the screen.

The view is the *wrapper made visible*: the guardrail decision and why, the retry
count the correction loop spent, the token/cost the run burned, and the terminal
state it bucketed into.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eval.cost import cost_usd
from eval.harness import classify_terminal_state
from nl2sql.pipeline.generate import DEFAULT_DIALECT, DEFAULT_MODEL
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.redact import NO_REDACTION, RedactionPolicy


@dataclass(frozen=True)
class DemoView:
    """Everything the UI renders for one question — the wrapper, made visible.

    Carries only the **presented (redacted)** result, never the raw verified rows
    the harness scores — so the demo cannot leak PII (CLAUDE.md §5.3).
    """

    question: str
    model: str
    db_id: str
    dialect: str
    candidate_sql: str | None
    # The deterministic guardrail decision and its reason (rule: why) — no rows.
    guard_allowed: bool
    guard_rule: str | None
    guard_reason: str | None
    # How many generate→execute cycles the capped correction loop spent.
    attempts: int
    terminal_state: str
    # Cost of the run: token usage, the dated-list-table price, and the
    # provider-reported price when the backend surfaced one (``None`` otherwise).
    input_tokens: int
    output_tokens: int
    list_cost_usd: float | None
    provider_cost_usd: float | None
    # The presented (redacted) result — masked PII; ``None`` when the run errored
    # or was guard-rejected and so produced no result to present.
    presented_columns: list[str] | None
    presented_rows: list[tuple[Any, ...]] | None
    # The execution error text, if any (a DB error — never result rows).
    error: str | None


def run_demo(
    question: str,
    *,
    engine: Any,
    schema: str,
    db_id: str = "payments",
    dialect: str = DEFAULT_DIALECT,
    model: str = DEFAULT_MODEL,
    redaction_policy: RedactionPolicy = NO_REDACTION,
    client: Any | None = None,
    max_attempts: int = 1,
) -> DemoView:
    """Run ``question`` through the shared pipeline and project a :class:`DemoView`.

    ``engine``/``schema`` point the run at a database (the payments Postgres demo
    or a BIRD SQLite db); ``redaction_policy`` masks the schema's PII columns on
    the presented exit. ``client`` is injectable so tests run without a model.
    ``max_attempts > 1`` arms the capped self-correction loop (pass@k), so the
    UI can show the retry count actually do something. Terminal state is read from
    the **harness** classifier — no comparison is passed (the demo has no gold), so
    a clean run buckets to ``success`` rather than ``wrong_answer``.
    """
    state = run_pipeline(
        question,
        schema=schema,
        engine=engine,
        db_id=db_id,
        dialect=dialect,
        model=model,
        client=client,
        max_attempts=max_attempts,
        redaction_policy=redaction_policy,
    )
    terminal = classify_terminal_state(state)
    in_tokens = int(state.meta.get("input_tokens", 0))
    out_tokens = int(state.meta.get("output_tokens", 0))
    return DemoView(
        question=question,
        model=model,
        db_id=db_id,
        dialect=dialect,
        candidate_sql=state.candidate_sql,
        guard_allowed=not state.guard_rejected,
        guard_rule=state.guard_rule,
        guard_reason=state.guard_reason,
        attempts=state.attempts,
        terminal_state=terminal.value,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        list_cost_usd=cost_usd(model, in_tokens, out_tokens),
        provider_cost_usd=state.meta.get("cost_usd"),
        presented_columns=state.presented_columns,
        presented_rows=state.presented_rows,
        error=state.error,
    )
