"""Self-correction where it can actually fire: the twin on the large-schema slice.

Step 5 measured the pass@1 → pass@k gap on the small Step-3 slice and found
**+0.000** — the correction loop *never fired*, because a strong model on small
schemas produced ~zero execution errors, and the loop can only feed back an
execution error. That was an honest zero, not a failure.

This points the **same twin** at the Step-6 **large-schema** slice (naive
full-schema dump, up to 14 tables) and lets the **generator model** vary (the
``MODEL`` env var). The model self-corrects itself — it is a fixed per-run input,
not swapped between attempts — so the gap measures what self-correction is worth
*for that model*, with no stronger model bailing it out. The lever the loop's
value actually turns on is **generator weakness**: a strong model writes valid
SQL even on a 14-table schema (nothing to correct → gap 0), while a weaker model
produces the malformed SQL the loop can recover.

Honest either way: if a run produces no recoverable execution errors, the gap is
still 0 — and the terminal-state decomposition below says so, showing the
eligible-error population the loop had to work with.

    uv run python -m eval.eval_bird_selfcorrect            # default model, k=3
    RETRY_BUDGET=5 uv run python -m eval.eval_bird_selfcorrect   # sweep the budget
    MODEL=openrouter/moonshotai/kimi-k2.7-code \
        uv run python -m eval.eval_bird_selfcorrect       # a weaker generator
"""

from __future__ import annotations

import logging
import sys
from datetime import date

from dotenv import load_dotenv

from eval.datasets.bird.slice_large import load_large_slice_ids
from eval.eval_bird import DIALECT, RESULTS_PATH, _git_commit, build_bird_cases
from eval.eval_bird_rag import slice6_id
from eval.eval_bird_twin import append_results, retry_budget

# Reuse the cross-provider factory: it binds a *specific* model into the
# import-shared pipeline (OpenRouter routing pinned, provider errors bucketed
# rather than crashing the run) — so the same runner can sweep the generator from
# strong to weak, which is the lever self-correction's value actually turns on.
from eval.eval_cross_provider import make_factory, provider_errors
from eval.harness import batch_session_id, derive_pass1_report, run_batch
from eval.metrics import TwinReport, twin_summary_lines
from eval.model_select import model_id  # MODEL env override → generator model
from nl2sql import obs
from nl2sql.pipeline.state import TerminalState
from nl2sql.prompts import PROMPT_VERSION


def _eligible_errors(twin: TwinReport) -> int:
    """Attempt-1 failures the loop *could* act on: execution errors (or exhausted)."""
    counts = twin.pass1.terminal_counts()
    return (
        counts[TerminalState.EXECUTION_ERROR_FINAL]
        + counts[TerminalState.RETRY_EXHAUSTED]
    )


def results_row(twin: TwinReport, *, k: int, model: str, commit: str) -> str:
    """RESULTS.md row for the large-schema self-correction run (CLAUDE.md §6)."""
    p1, pk = twin.pass1, twin.passk
    number = (
        f"{twin.pass_at_1:.3f} ({p1.n_correct}/{p1.total}) → "
        f"{twin.pass_at_k:.3f} ({pk.n_correct}/{pk.total}) "
        f"[gap {twin.gap:+.3f}; {_eligible_errors(twin)} exec-err eligible]"
    )
    return (
        f"| {date.today().isoformat()} | 5 | self-correction on large schemas "
        f"(pass@1→pass@{k}) | {number} | {model} | {slice6_id()} | "
        f"{PROMPT_VERSION} | {commit} |"
    )


def results_prose(twin: TwinReport, *, k: int, model: str) -> str:
    """The plain-language finding: did big schemas give the loop anything to fix?"""
    counts = twin.pass1.terminal_counts()
    eligible = _eligible_errors(twin)
    wrong = counts[TerminalState.WRONG_ANSWER]
    rejected = counts[TerminalState.GUARDRAIL_REJECTED]
    failed = twin.pass1.total - twin.pass1.n_correct

    head = (
        f"**Step 5 follow-up — self-correction where it can fire (large schemas).** "
        f"Step 5's +0.000 gap was an *eligibility* result, not a verdict on "
        f"correction: the loop only feeds back execution errors, and the small "
        f"Step-3 slice produced none. Re-running the **same twin** on the frozen "
        f"`{slice6_id()}` slice (naive full-schema dump, up to 14 tables) gives "
        f"**pass@1 {twin.pass_at_1:.3f} ({twin.pass1.n_correct}/{twin.pass1.total})** "
        f"→ **pass@{k} {twin.pass_at_k:.3f} "
        f"({twin.passk.n_correct}/{twin.passk.total})** — gap **{twin.gap:+.3f}**. "
    )
    more = "did" if eligible else "did not"
    breakdown = (
        f"Of the **{failed}** pass@1 failures, **{eligible}** were execution errors "
        f"(the loop's eligible set — the bigger schemas {more} give it more to work "
        f"with than Step 3's zero), **{wrong}** were "
        f"wrong-answers (clean execution, wrong result — semantic, not the loop's "
        f"job), and **{rejected}** were guardrail rejections. "
    )
    if twin.added_attempts == 0:
        tail = (
            f"The loop **never fired** — even on these schemas the model's invalid "
            f"queries were {'caught by the guard' if rejected else 'absent'}, so the "
            f"gap is **0** and the added cost is **exactly 0**. The honest reading "
            f"holds: self-correction recovers *syntactic* failures, and this "
            f"workload's failures are *semantic*. "
        )
    else:
        recovered = round(twin.recovery_rate * failed)
        cost = (
            f"${twin.added_cost_usd:+.4f}"
            if twin.added_cost_usd is not None
            else f"unavailable for {model}"
        )
        tail = (
            f"It recovers **{recovered}/{failed}** "
            f"(**{twin.recovery_rate:.0%}**) of the failures at a cost of "
            f"**{twin.added_attempts} extra generate→execute cycles**, "
            f"**{twin.added_latency_ms:+.0f} ms** added wall-clock, and **{cost}** "
            f"added spend ({model}) — the lift reported with its price, never "
            f"without (the silent-retry pitfall the twin guards against). "
        )
    foot = "Reproduce with `uv run python -m eval.eval_bird_selfcorrect`."
    return head + breakdown + tail + foot


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    k = retry_budget()
    model = model_id()
    cases, evidence = build_bird_cases(slice_ids=load_large_slice_ids())
    print(
        f"self-correction twin: {len(cases)} large-schema BIRD questions "
        f"({DIALECT}, naive dump) on `{model}`; one pass@{k} run, pass@1 derived "
        f"from its first attempts…"
    )
    passk = run_batch(
        cases,
        make_factory(model, evidence)(k),
        session_id=batch_session_id(
            f"bird-selfcorrect-pass{k}", model=model, prompt_version=PROMPT_VERSION
        ),
    )
    pass1 = derive_pass1_report(passk)
    twin = TwinReport(pass1=pass1, passk=passk, model=model)

    print("\n" + "\n".join(twin_summary_lines(twin)))
    print(f"eligible execution errors (pass@1): {_eligible_errors(twin)}")
    n_provider_errors = provider_errors(passk)
    if n_provider_errors:
        print(
            f"provider errors (infra, not SQL): {n_provider_errors}/{twin.passk.total}"
        )

    commit = _git_commit()
    row = results_row(twin, k=k, model=model, commit=commit)
    prose = results_prose(twin, k=k, model=model)
    print("\nRESULTS.md row:\n" + row)
    if write:
        append_results(row, prose)
        print(f"\nappended to {RESULTS_PATH.name}")
    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
