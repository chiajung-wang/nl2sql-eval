"""Batch runner: question → result, scored and bucketed.

For each question: run the pipeline, score via canonicalized result-set
comparison (upstream of redaction), classify the terminal state, and record
cost/latency/attempts. Reports pass@1 and pass@k and retrieval recall. The
terminal-state classifier lives here, not in ``state.py``.

Step 1 (issue 5) wires only the slice of the classifier the end-to-end proof
needs — the two states reachable so far, ``success`` and
``execution_error_final``. The batch runner, gold scoring, and the remaining
four terminal states land from Step 3 onward.
"""

from __future__ import annotations

from nl2sql.pipeline.state import RunState, TerminalState


def classify_terminal_state(state: RunState) -> TerminalState:
    """Bucket a finished run into exactly one terminal state.

    Step-1 scope (issue 5): a captured execution error buckets as
    ``EXECUTION_ERROR_FINAL``; an otherwise-clean run buckets as ``SUCCESS``.
    The comparator-dependent ``WRONG_ANSWER`` and the retrieval/guardrail/retry
    states become reachable only as those stages and the scorer land (Step 2+);
    this function grows to cover them then. The classifier lives in the harness,
    never in ``state.py`` (CLAUDE.md §3).

    Step-1 caveat: a *generation* gap (``execute`` sets ``state.error`` to
    "no candidate SQL to execute" when no SQL was produced) also buckets here,
    since ``generate`` is the only upstream stage and has no retry budget yet.
    A retry/generation-failure state splits this out when self-correction lands
    (Step 5); until then ``EXECUTION_ERROR_FINAL`` is the catch-all for any
    captured error.
    """
    if state.error is not None:
        return TerminalState.EXECUTION_ERROR_FINAL
    return TerminalState.SUCCESS
