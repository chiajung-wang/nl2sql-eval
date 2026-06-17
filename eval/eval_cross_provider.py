"""Step 7 Definition of Done: the cross-provider table (accuracy × cost × latency).

Runs the **import-shared** pipeline over the frozen BIRD slice once per model in
``CROSS_PROVIDER_MODELS`` and reports, per model, **pass@1 / pass@k accuracy ×
cost × latency** — turning "model selection / cost-latency-quality trade-offs"
(a JKOPay JD requirement) into a concrete eval artifact. Every model call goes
through the LiteLLM boundary (#51); the backend is the model identifier, so one
``OPENROUTER_API_KEY`` reaches many providers via ``openrouter/<provider>/<model>``.

Two honesty rails the plan calls out:

- **Cost basis is recorded per row.** An ``openrouter/…`` row is priced by
  OpenRouter's *own* reported cost (surfaced by LiteLLM on the response), not the
  direct-list table in ``eval.cost`` — they differ, so the table says which basis
  each row used. A direct ``anthropic/…`` row uses the dated list table.
- **OpenRouter routing is pinned** (``allow_fallbacks: false``) so a frozen-slice
  row can't silently switch backend mid-run and break repeatability (PRD §9).

    uv run python -m eval.eval_cross_provider            # run + append RESULTS.md
    uv run python -m eval.eval_cross_provider --dry-run  # run + print, no write
    CROSS_PROVIDER_MODELS="openrouter/a/m1,openrouter/b/m2" \
        uv run python -m eval.eval_cross_provider        # compare a model list

pass@1 is derived from the pass@k run's first attempts (the sampling-noise-free
twin, as in ``eval.eval_bird_twin``). The single-model default run also serves as
the **post-refactor parity check** for #50/#51: same model, same slice, the
number must match the Step-3/Step-5 baseline.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from eval.eval_bird import (
    DIALECT,
    RESULTS_PATH,
    _engine,
    _git_commit,
    _schema,
    build_bird_cases,
    slice_id,
)
from eval.harness import Case, RunOne, derive_pass1_report, run_batch
from eval.metrics import BatchReport
from nl2sql.llm import LiteLLMClient, LLMClient
from nl2sql.pipeline.generate import DEFAULT_MODEL, PROMPT_VERSION
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState

DEFAULT_RETRY_BUDGET = 3

# Pin OpenRouter's provider routing so a frozen-slice row can't switch backend
# (or quantization) mid-run — repeatability is a Step-7/PRD §9 invariant. Passed
# verbatim to litellm.completion via the LiteLLMClient extra_params hook (#51).
OPENROUTER_ROUTING_PIN: dict[str, object] = {"provider": {"allow_fallbacks": False}}

# A RESULTS.md Log-table row starts with a date: ``| YYYY-MM-DD |``. Used to
# anchor the insert past any markdown tables embedded in later steps' prose.
_LOG_ROW_RE = re.compile(r"\| \d{4}-\d{2}-\d{2} \|")


def cross_provider_models() -> list[str]:
    """The model list from ``CROSS_PROVIDER_MODELS`` (comma-separated).

    Falls back to the single default model when unset — then the run is the
    post-refactor parity check rather than a cross-provider comparison.
    """
    raw = os.environ.get("CROSS_PROVIDER_MODELS", "").strip()
    if not raw:
        return [DEFAULT_MODEL]
    return [m.strip() for m in raw.split(",") if m.strip()]


def retry_budget() -> int:
    """The pass@k budget ``k`` — ``RETRY_BUDGET`` env var or the default 3."""
    return int(os.environ.get("RETRY_BUDGET", DEFAULT_RETRY_BUDGET))


def cost_basis(model: str) -> str:
    """Which price basis a row uses: OpenRouter's reported cost vs. the list table."""
    return "openrouter" if model.startswith("openrouter/") else "direct-list"


def make_client(model: str) -> LLMClient | None:
    """The client for ``model``: an ``openrouter/…`` id gets routing pinned; a
    direct provider id uses the default client (LiteLLM reads its env key)."""
    if model.startswith("openrouter/"):
        return LiteLLMClient(extra_params=OPENROUTER_ROUTING_PIN)
    return None


def row_cost(model: str, passk: BatchReport) -> float | None:
    """The row's total cost on its declared basis.

    OpenRouter rows use the **provider-reported** cost (the authentic OpenRouter
    price, ``None`` if the backend surfaced none); direct rows use the dated list
    table by model (``None`` if unpriced).
    """
    if model.startswith("openrouter/"):
        return passk.provider_cost_usd
    return passk.cost_usd(model)


@dataclass(frozen=True)
class ProviderRow:
    """One model's line in the cross-provider table."""

    model: str
    total: int
    n_correct_1: int
    n_correct_k: int
    cost_usd: float | None
    cost_basis: str
    mean_latency_ms: float
    provider_errors: int = 0

    @property
    def pass1(self) -> float:
        return self.n_correct_1 / self.total if self.total else 0.0

    @property
    def passk(self) -> float:
        return self.n_correct_k / self.total if self.total else 0.0


def provider_row(model: str, passk: BatchReport) -> ProviderRow:
    """Build a table row from a model's pass@k batch (pass@1 derived from it)."""
    pass1 = derive_pass1_report(passk)
    return ProviderRow(
        model=model,
        total=passk.total,
        n_correct_1=pass1.n_correct,
        n_correct_k=passk.n_correct,
        cost_usd=row_cost(model, passk),
        cost_basis=cost_basis(model),
        mean_latency_ms=passk.mean_latency_ms,
        provider_errors=provider_errors(passk),
    )


def render_table(rows: list[ProviderRow], *, k: int) -> str:
    """The markdown cross-provider table (accuracy × cost × latency, basis noted).

    The ``provider errors`` column flags cases that failed at the provider (e.g.
    rate limits), so a depressed accuracy is read in context rather than as model
    quality.
    """
    head = (
        f"| model | pass@1 | pass@{k} | cost (USD) | cost basis | "
        f"mean latency (ms) | provider errors |\n"
        f"| --- | --- | --- | --- | --- | --- | --- |"
    )
    lines = [head]
    for r in rows:
        cost = f"${r.cost_usd:.4f}" if r.cost_usd is not None else "n/a"
        errs = f"{r.provider_errors}/{r.total}" if r.provider_errors else "0"
        lines.append(
            f"| `{r.model}` | {r.pass1:.3f} ({r.n_correct_1}/{r.total}) | "
            f"{r.passk:.3f} ({r.n_correct_k}/{r.total}) | {cost} | "
            f"{r.cost_basis} | {r.mean_latency_ms:.0f} | {errs} |"
        )
    return "\n".join(lines)


# Marks a case whose *generation call itself* failed (e.g. an OpenRouter 429
# rate limit), as opposed to a SQL execution error. A live run exposed that a
# single uncaught provider error aborted the whole multi-model job and wrote
# nothing — so the runner now captures it per case: the batch survives, the case
# buckets as an error, and the count is surfaced so a depressed accuracy is read
# as "infra failures", not the model being wrong.
PROVIDER_ERROR_PREFIX = "provider_error:"


def make_factory(model: str, evidence: dict[str, str]):
    """Bind the import-shared pipeline into a budget-parameterized runner.

    A provider/transport exception (rate limit, auth, transient 5xx) is caught
    and turned into an errored ``RunState`` rather than propagating — one model's
    bad spell can't discard the other models' completed work.
    """
    client = make_client(model)

    def factory(max_attempts: int) -> RunOne:
        def run_one(case: Case) -> RunState:
            try:
                return run_pipeline(
                    case.question,
                    schema=_schema(case.db_id),
                    engine=_engine(case.db_id),
                    db_id=case.db_id,
                    dialect=DIALECT,
                    evidence=evidence.get(case.id, ""),
                    model=model,
                    client=client,
                    max_attempts=max_attempts,
                )
            except Exception as e:  # noqa: BLE001 — provider failures are opaque
                state = RunState(
                    question=case.question, db_id=case.db_id, max_attempts=max_attempts
                )
                state.attempts = 1
                state.error = f"{PROVIDER_ERROR_PREFIX} {type(e).__name__}: {e}"
                return state

        return run_one

    return factory


def provider_errors(report: BatchReport) -> int:
    """How many cases failed at the provider (vs a SQL execution error)."""
    return sum(
        1
        for r in report.results
        if r.note is not None and r.note.startswith(PROVIDER_ERROR_PREFIX)
    )


def evaluate_model(
    model: str, cases: list[Case], evidence: dict[str, str], *, k: int
) -> ProviderRow:
    """Run the slice for one model (pass@k) and build its table row."""
    passk = run_batch(cases, make_factory(model, evidence)(k))
    return provider_row(model, passk)


def results_row(rows: list[ProviderRow], *, k: int, commit: str) -> str:
    """The RESULTS.md Log row — a one-line pointer to the table below it."""
    best = max(rows, key=lambda r: r.pass1) if rows else None
    number = (
        f"{len(rows)} models; best pass@1 {best.pass1:.3f} (`{best.model}`)"
        if best
        else "no models"
    )
    return (
        f"| {date.today().isoformat()} | 7 | cross-provider (pass@1/pass@{k}) | "
        f"{number} | cross-provider (see table) | {slice_id()} | "
        f"{PROMPT_VERSION} | {commit} |"
    )


def results_prose(rows: list[ProviderRow], *, k: int) -> str:
    """The Step-7 finding paragraph plus the cross-provider table."""
    head = (
        f"**Step 7 — cross-provider table (accuracy × cost × latency).** Over the "
        f"frozen `{slice_id()}` slice, the import-shared pipeline was run once per "
        f"model through the LiteLLM boundary (#51); pass@1 is derived from each "
        f"pass@{k} run's first attempts (no resampling noise). **Cost basis is "
        f"noted per row**: `openrouter` rows use OpenRouter's own reported price "
        f"(surfaced by LiteLLM), direct rows the dated list table in `eval.cost` — "
        f"the two are not comparable dollar-for-dollar. OpenRouter routing was "
        f"pinned (`allow_fallbacks: false`) for repeatability (PRD §9). Reproduce "
        f"with `uv run python -m eval.eval_cross_provider`."
    )
    total_errs = sum(r.provider_errors for r in rows)
    if total_errs:
        head += (
            f" **Caveat:** {total_errs} case(s) failed at the provider (e.g. "
            f"OpenRouter rate limits) — see the `provider errors` column; those "
            f"rows' accuracy is depressed by infra failures, not model quality."
        )
    return head + "\n\n" + render_table(rows, k=k)


def append_results(row: str, prose: str, results_path: Path = RESULTS_PATH) -> None:
    """Insert the Log ``row`` after the last *dated* Log row; append ``prose`` at EOF.

    Matching on a leading ``| YYYY-MM-DD |`` (not just any ``|`` line) is load-
    bearing: later steps embed their own markdown tables inside the prose, so the
    last ``|`` line in the file is an embedded table row, not the Log table — a
    naive "after the last table row" insert wedges the Log row inside that table.
    """
    lines = [
        ln
        for ln in results_path.read_text().splitlines()
        if not ln.strip().startswith("| _—_")
    ]
    dated = [i for i, ln in enumerate(lines) if _LOG_ROW_RE.match(ln.lstrip())]
    if not dated:
        raise ValueError("no dated Log row found in RESULTS.md to anchor the insert")
    lines.insert(dated[-1] + 1, row)
    text = "\n".join(lines).rstrip() + "\n\n" + prose + "\n"
    results_path.write_text(text)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)

    k = retry_budget()
    models = cross_provider_models()
    cases, evidence = build_bird_cases()
    print(
        f"cross-provider: {len(models)} model(s) × {len(cases)} BIRD questions "
        f"({DIALECT}, naive schema dump), pass@{k} with pass@1 derived…"
    )

    rows = [evaluate_model(m, cases, evidence, k=k) for m in models]

    table = render_table(rows, k=k)
    print("\n" + table)
    commit = _git_commit()
    row = results_row(rows, k=k, commit=commit)
    print("\nRESULTS.md row:\n" + row)
    if write:
        append_results(row, results_prose(rows, k=k))
        print(f"\nappended to {RESULTS_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
