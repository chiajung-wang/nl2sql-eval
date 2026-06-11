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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from eval.compare import DEFAULT_RULES, Comparison, compare
from eval.metrics import BatchReport, CaseResult
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


def classify_terminal_state(
    state: RunState, comparison: Comparison | None = None
) -> TerminalState:
    """Bucket a finished run into exactly one terminal state.

    Reachable as of Step 3:

    - a captured error → ``EXECUTION_ERROR_FINAL``;
    - a clean run whose result the comparator judged wrong → ``WRONG_ANSWER``;
    - a clean run whose result matched gold → ``SUCCESS``.

    ``comparison`` is the scorer's verdict (``None`` when the run errored and was
    never scored, or for callers that only classify execution outcome — e.g. the
    Step-1 proof, which passes no comparison and so never sees ``WRONG_ANSWER``).
    The ``GUARDRAIL_REJECTED``, ``RETRIEVAL_EMPTY``, and ``RETRY_EXHAUSTED`` states
    become reachable only as those stages land (Step 4–6). The classifier lives
    in the harness, never in ``state.py`` (CLAUDE.md §3).

    Step-1 caveat (unchanged): a *generation* gap (``execute`` sets ``state.error``
    when no SQL was produced) also buckets as ``EXECUTION_ERROR_FINAL``, since
    ``generate`` has no retry budget yet; a generation-failure state splits this
    out when self-correction lands (Step 5).
    """
    if state.error is not None:
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
    that errored is not scored (there is no candidate result to compare).
    """
    comparison: Comparison | None = None
    if state.error is None:
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
        state = run_one(case)
        comparison, terminal = score_run(state, case, rules=rules)
        correct = terminal is TerminalState.SUCCESS
        note = (
            state.error
            if state.error is not None
            else (comparison.reason if comparison is not None else None)
        )
        results.append(
            CaseResult(
                case_id=case.id,
                db_id=case.db_id,
                terminal_state=terminal,
                correct=correct,
                difficulty=case.difficulty,
                candidate_sql=state.candidate_sql,
                note=note,
            )
        )
        logger.info(
            "harness case=%s db=%s terminal=%s correct=%s",
            case.id,
            case.db_id,
            terminal.value,
            correct,
        )
    return BatchReport(tuple(results))
