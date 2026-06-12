"""Batch runner: question → result, scored and bucketed.

For each question: run the pipeline (the **import-shared** ``run_pipeline`` — never
a fork, so the harness measures exactly what the demo runs), score via the
canonicalized result-set comparator (upstream of redaction), and classify the
terminal state. Aggregation into pass@1 lives in ``eval/metrics.py``; the
terminal-state **classifier lives here, not in ``state.py``** (CLAUDE.md §3).

Step 3 makes ``success``, ``wrong_answer``, and ``execution_error_final``
reachable — pass@1 is the only meaningful metric (no self-correction yet). The
``run_one`` callable is injected so the live entrypoints (``eval.eval_payments``,
and the BIRD runner from Issue 2) wire it to the real pipeline while tests pass a
stub — the harness logic is exercised offline, no DB or network required.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from eval.compare import DEFAULT_RULES, Comparison, compare
from eval.metrics import BatchReport, CaseResult, TwinReport
from nl2sql.pipeline.state import RunState, TerminalState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Case:
    """One evaluation question: everything the harness needs to run and score it.

    ``db_id`` is an input — the question is tagged with its database (single-db
    per run; cross-db routing is out of scope, CLAUDE.md §5.8).
    """

    id: str
    question: str
    db_id: str
    gold_sql: str
    gold_result: Mapping[str, Any]
    difficulty: str | None = None


# Injected per-question runner: takes a Case, returns its finished RunState. The
# live entrypoints bind this to the import-shared pipeline; tests pass a stub.
RunOne = Callable[[Case], RunState]

# A factory that binds a retry budget into a runner: ``factory(1)`` is the
# single-shot pass@1 runner, ``factory(k)`` the correction-on pass@k runner. The
# twin metric runs the *same* cases through both (Step 5, issue #43).
RunOneFactory = Callable[[int], RunOne]


def classify_terminal_state(
    state: RunState, comparison: Comparison | None = None
) -> TerminalState:
    """Bucket a finished run into exactly one terminal state.

    Reachable as of Step 5:

    - a candidate the guard gate rejected pre-execution → ``GUARDRAIL_REJECTED``;
    - an error after the correction loop spent its budget → ``RETRY_EXHAUSTED``;
    - an error on a single-shot run (no retry budget) → ``EXECUTION_ERROR_FINAL``;
    - a clean run whose result the comparator judged wrong → ``WRONG_ANSWER``;
    - a clean run whose result matched gold → ``SUCCESS``.

    The guard check comes first: a rejected candidate never executed and was never
    scored, so it must not fall through to the error/answer buckets. ``comparison``
    is the scorer's verdict (``None`` when the run errored or was guard-rejected
    and so never scored, or for callers that only classify execution outcome —
    e.g. the Step-1 proof, which passes no comparison and so never sees
    ``WRONG_ANSWER``).

    The error split is keyed off ``state.attempts``: the Step-5 retry loop only
    returns an errored run after spending its budget, so ``attempts > 1`` means
    the correction loop ran and still failed (``RETRY_EXHAUSTED``), while a
    single-shot failure — pass@1 mode, or a generation gap that produced no SQL —
    keeps the prior ``EXECUTION_ERROR_FINAL`` bucket. ``RETRIEVAL_EMPTY`` becomes
    reachable when schema-RAG lands (Step 6). The classifier lives in the harness,
    never in ``state.py`` (CLAUDE.md §3).
    """
    if state.guard_rejected:
        return TerminalState.GUARDRAIL_REJECTED
    if state.error is not None:
        if state.attempts > 1:
            return TerminalState.RETRY_EXHAUSTED
        return TerminalState.EXECUTION_ERROR_FINAL
    if comparison is not None and not comparison.correct:
        return TerminalState.WRONG_ANSWER
    return TerminalState.SUCCESS


def score_run(
    state: RunState, case: Case, *, rules: Sequence[str] = DEFAULT_RULES
) -> tuple[Comparison | None, TerminalState]:
    """Score a finished run against gold and bucket its terminal state.

    Scoring is on the **raw verified result** — ``state.result_rows`` — which is
    correct only because the pipeline has no ``redact`` stage yet; once it does,
    this must score the raw exit, never the presented one (CLAUDE.md §5.2). A run
    that errored or was guard-rejected is not scored (there is no candidate result
    to compare).
    """
    comparison: Comparison | None = None
    if not state.guard_rejected and state.error is None:
        candidate = {
            "columns": state.result_columns or [],
            "rows": state.result_rows or [],
        }
        comparison = compare(case.gold_result, candidate, case.gold_sql, rules=rules)
    terminal = classify_terminal_state(state, comparison)
    return comparison, terminal


def run_batch(
    cases: Sequence[Case],
    run_one: RunOne,
    *,
    rules: Sequence[str] = DEFAULT_RULES,
) -> BatchReport:
    """Run each case through ``run_one``, score it, and aggregate into a report.

    Batch-capable, offline, repeatable — invokable as a job (this is what enables
    prompt-CI later). Logs per-case the verdict and terminal state, **never the
    result rows** (the comparator runs upstream of redaction, CLAUDE.md §5.3).
    """
    results: list[CaseResult] = []
    for case in cases:
        start = time.perf_counter()
        state = run_one(case)
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        comparison, terminal = score_run(state, case, rules=rules)
        correct = terminal is TerminalState.SUCCESS
        if state.guard_rejected:
            note = state.guard_reason
        elif state.error is not None:
            note = state.error
        else:
            note = comparison.reason if comparison is not None else None
        results.append(
            CaseResult(
                case_id=case.id,
                db_id=case.db_id,
                terminal_state=terminal,
                correct=correct,
                difficulty=case.difficulty,
                candidate_sql=state.candidate_sql,
                note=note,
                # Cost of the run: attempts the correction loop spent (≥1) and the
                # accumulated token usage, so pass@k's lift is shown against its
                # price (Step 5, issue #43). Latency is wall-clock around the whole
                # run — every attempt included.
                attempts=state.attempts or 1,
                input_tokens=int(state.meta.get("input_tokens", 0) or 0),
                output_tokens=int(state.meta.get("output_tokens", 0) or 0),
                latency_ms=latency_ms,
            )
        )
        logger.info(
            "harness case=%s db=%s terminal=%s correct=%s attempts=%s",
            case.id,
            case.db_id,
            terminal.value,
            correct,
            state.attempts or 1,
        )
    return BatchReport(tuple(results))


def run_twin(
    cases: Sequence[Case],
    run_one_factory: RunOneFactory,
    *,
    k: int,
    model: str,
    rules: Sequence[str] = DEFAULT_RULES,
) -> TwinReport:
    """Run the slice twice — correction off then on — into a :class:`TwinReport`.

    pass@1 is ``run_one_factory(1)`` (single shot); pass@k is
    ``run_one_factory(k)`` (the capped correction budget). Same cases, same
    comparator, both scored by :func:`run_batch`; the report holds the gap and the
    added cost/latency. ``model`` prices both batches. This is the harness's job —
    the live entrypoint only supplies the factory that binds the budget into the
    import-shared pipeline (Step 5, issue #43).
    """
    pass1 = run_batch(cases, run_one_factory(1), rules=rules)
    passk = run_batch(cases, run_one_factory(k), rules=rules)
    return TwinReport(pass1=pass1, passk=passk, model=model)
