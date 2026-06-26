"""Step 5 Definition of Done: the pass@1 → pass@k gap over the frozen BIRD slice.

Runs the **import-shared** pipeline once over the frozen slice with the capped
correction budget on (pass@k), then **derives pass@1 from that same run's first
attempts** — the rigorous, sampling-noise-free twin (a second independent run
would let a question flip wrong→right just by resampling, with no correction
involved). Reports the gap together with the **added cost and latency** that buys
it. This is one of the two sharpest findings in the project: "self-correction
recovers X% of initial failures at a cost of Y" (CLAUDE.md §6, PRD §10). The
number is appended to ``RESULTS.md`` with full config.

The pass@1 here is the same naive schema-dump baseline as Step 3 (whole schema in
the prompt, SQLite dialect, BIRD evidence hint), now on ``generate/v3`` — which is
byte-identical to v2 when correction is off, so pass@1 is comparable across the
two steps. Reuses the Step-3 BIRD plumbing (cases, engines, schema, slice id).

    uv run python -m eval.eval_bird_twin            # run + append RESULTS.md
    uv run python -m eval.eval_bird_twin --dry-run  # run + print, no RESULTS.md write
    RETRY_BUDGET=5 uv run python -m eval.eval_bird_twin   # override the budget (k)
"""

from __future__ import annotations

import logging
import os
import sys
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
from eval.harness import (
    Case,
    RunOne,
    batch_session_id,
    derive_pass1_report,
    run_batch,
)
from eval.metrics import TwinReport, twin_summary_lines
from eval.model_select import model_id
from nl2sql import obs
from nl2sql.pipeline.generate import DEFAULT_MODEL
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState, TerminalState
from nl2sql.prompts import PROMPT_VERSION

DEFAULT_RETRY_BUDGET = 3


def retry_budget() -> int:
    """The pass@k budget ``k`` — ``RETRY_BUDGET`` env var or the default 3."""
    return int(os.environ.get("RETRY_BUDGET", DEFAULT_RETRY_BUDGET))


def make_factory(evidence: dict[str, str], model: str = DEFAULT_MODEL):
    """Bind the import-shared pipeline into a budget-parameterized runner factory.

    ``factory(1)`` is the single-shot pass@1 runner; ``factory(k)`` enables the
    capped correction loop — the harness runs the same cases through both.
    ``model`` selects the generator (the ``MODEL`` env override resolves to it).
    """

    def factory(max_attempts: int) -> RunOne:
        def run_one(case: Case) -> RunState:
            return run_pipeline(
                case.question,
                schema=_schema(case.db_id),
                engine=_engine(case.db_id),
                db_id=case.db_id,
                dialect=DIALECT,
                evidence=evidence.get(case.id, ""),
                max_attempts=max_attempts,
                model=model,
            )

        return run_one

    return factory


def results_row(
    twin: TwinReport, *, k: int, model: str, prompt_version: str, commit: str
) -> str:
    """The RESULTS.md table row for the twin run (CLAUDE.md §6 — full config)."""
    p1 = twin.pass1
    pk = twin.passk
    number = (
        f"{twin.pass_at_1:.3f} ({p1.n_correct}/{p1.total}) → "
        f"{twin.pass_at_k:.3f} ({pk.n_correct}/{pk.total}) "
        f"[gap {twin.gap:+.3f}]"
    )
    metric = f"pass@1→pass@{k}"
    return (
        f"| {date.today().isoformat()} | 5 | {metric} | {number} | "
        f"{model} | {slice_id()} | {prompt_version} | {commit} |"
    )


def results_prose(twin: TwinReport, *, k: int, model: str) -> str:
    """The plain-language Step-5 finding paragraph appended under the table.

    Explains the gap, not just states it: the execution-error loop can only act on
    runs that *errored*, so the paragraph breaks pass@1's failures into
    execution-errors (eligible for retry) vs wrong-answers/guard-rejections (which
    the loop correctly leaves alone). When no correction fired, it says so plainly
    — and notes that the cost/latency delta is then run-to-run variance, not the
    price of correction.
    """
    counts = twin.pass1.terminal_counts()
    err_failures = (
        counts[TerminalState.EXECUTION_ERROR_FINAL]
        + counts[TerminalState.RETRY_EXHAUSTED]
    )
    wrong = counts[TerminalState.WRONG_ANSWER]
    rejected = counts[TerminalState.GUARDRAIL_REJECTED]
    failed = twin.pass1.total - twin.pass1.n_correct

    head = (
        f"**Step 5 — pass@1 → pass@{k} gap (what self-correction is worth).** "
        f"Over the frozen BIRD slice, enabling the capped execution-error "
        f"correction loop moves accuracy from **pass@1 {twin.pass_at_1:.3f} "
        f"({twin.pass1.n_correct}/{twin.pass1.total})** to **pass@{k} "
        f"{twin.pass_at_k:.3f} ({twin.passk.n_correct}/{twin.passk.total})** — a "
        f"gap of **{twin.gap:+.3f}**. "
    )
    breakdown = (
        f"Of the **{failed}** pass@1 failures, **{err_failures}** were execution "
        f"errors (the only kind the loop can feed back), **{wrong}** were "
        f"wrong-answers (clean execution, wrong result), and **{rejected}** were "
        f"guardrail rejections. "
    )
    if twin.added_attempts == 0:
        tail = (
            f"The loop **never fired** — there were no execution errors to "
            f"correct — so the gap is necessarily **0**, and the cost/latency "
            f"delta is **exactly 0** (pass@1 is derived from this same run's first "
            f"attempts, so with no retries the two views are identical — no "
            f"second run, no sampling noise). The honest reading: on this slice "
            f"the failures are **semantic, not syntactic** — recovering them needs "
            f"better retrieval/generation (Step 6), not retry. This is exactly "
            f"where the twin metric earns its keep: it proves self-correction adds "
            f"no accuracy here rather than letting a headline pass@{k} imply "
            f"otherwise. "
        )
    else:
        recovered = round(twin.recovery_rate * failed)
        cost = _cost_phrase(twin.added_cost_usd, model)
        tail = (
            f"It recovers **{recovered}/{failed}** (**{twin.recovery_rate:.0%}**) "
            f"of those failures at a cost of **{twin.added_attempts} extra "
            f"generate→execute cycles**, **{twin.added_latency_ms:+.0f} ms** "
            f"added wall-clock total, and **{cost}** added spend ({model}) — the "
            f"lift is never reported without its price (the silent-retry pitfall "
            f"this twin metric guards against). "
        )
    foot = (
        "pass@1 matches the Step-3 baseline (`generate/v3` renders "
        "byte-identical to v2 with correction off). Reproduce with "
        "`uv run python -m eval.eval_bird_twin`."
    )
    return head + breakdown + tail + foot


def _cost_phrase(added_cost: float | None, model: str) -> str:
    return (
        f"${added_cost:+.4f}" if added_cost is not None else f"unavailable for {model}"
    )


def append_results(row: str, prose: str, results_path: Path = RESULTS_PATH) -> None:
    """Insert the table ``row`` after the last log row and append ``prose`` at EOF.

    The Step-5 row joins the Log table (it must sit with the other rows, not after
    the trailing prose), while the finding paragraph is appended after everything.
    Any leftover placeholder row is retired.
    """
    lines = [
        ln
        for ln in results_path.read_text().splitlines()
        if not ln.strip().startswith("| _—_")
    ]
    # The last line that opens with "|" is the final existing table row.
    last_row = max(i for i, ln in enumerate(lines) if ln.lstrip().startswith("|"))
    lines.insert(last_row + 1, row)
    text = "\n".join(lines).rstrip() + "\n\n" + prose + "\n"
    results_path.write_text(text)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    k = retry_budget()
    model = model_id()
    cases, evidence = build_bird_cases()
    print(
        f"twin-scoring {len(cases)} BIRD questions ({DIALECT}, naive schema dump) "
        f"on `{model}`: one pass@{k} run (budget {k}); pass@1 derived from first "
        f"attempts…"
    )
    passk = run_batch(
        cases,
        make_factory(evidence, model)(k),
        session_id=batch_session_id(
            f"bird-twin-pass{k}", model=model, prompt_version=PROMPT_VERSION
        ),
    )
    pass1 = derive_pass1_report(passk)
    twin = TwinReport(pass1=pass1, passk=passk, model=model)

    print("\n" + "\n".join(twin_summary_lines(twin)))
    commit = _git_commit()
    row = results_row(
        twin, k=k, model=model, prompt_version=PROMPT_VERSION, commit=commit
    )
    prose = results_prose(twin, k=k, model=model)
    print("\nRESULTS.md row:\n" + row)
    if write:
        append_results(row, prose)
        print(f"\nappended to {RESULTS_PATH.name}")
    # Short-lived job: export buffered Langfuse spans before exit. A no-op offline
    # and redundant with the SDK's atexit flush, but makes export deterministic.
    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
