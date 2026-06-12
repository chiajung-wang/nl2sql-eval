"""Stage: correct — execution-error feedback loop.

Turns a failed execution into a correction signal for the next ``generate``,
within the capped retry budget the graph enforces. Arrives at Step 5.

**Scope (Step 5): execution-error feedback only.** The stage captures the failed
candidate SQL and the database error and stages them on ``state.correction`` so
the next ``generate`` can render them into the prompt (prompts/generate/v3.jinja)
and try again. The retrieval re-trigger (column/table-not-found → re-retrieve) is
a Step-6 contribution — schema-RAG does not exist yet, so the loop cannot
re-trigger a retrieval that isn't there (plan-step-5 "Explicitly NOT in this
step"). Guardrail-rejection feedback is likewise deferred; a rejected candidate
is terminal here.

No prompt strings live here (CLAUDE.md §4): this stage assembles only the
*data* (prior SQL + error) of the correction. The wording that frames it lives in
the externalized template under ``{% if correction %}``.
"""

from __future__ import annotations

from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState


def correct(state: RunState) -> RunState:
    """Stage the prior failure as a correction signal and clear it for a retry.

    Reads the failed attempt's ``candidate_sql`` and ``error`` onto
    ``state.correction`` (the structured feedback the next ``generate`` renders),
    then clears ``error`` and the empty result so the next generate→execute cycle
    starts clean. Only the error class is attached to the obs span — never row
    values, which never reach a failed run anyway. Mutates and returns ``state``.

    A no-op (correction stays ``None``) when there is no error to feed back, so a
    stray call cannot fabricate a correction signal.
    """
    with stage_span("correct", db_id=state.db_id, attempt=state.attempts) as extra:
        if state.error is None:
            extra["corrected"] = False
            return state

        state.correction = {
            "sql": state.candidate_sql or "",
            "error": state.error,
        }
        # Drop the failed attempt so the next cycle is scored on its own outcome.
        state.error = None
        state.result_rows = None
        state.result_columns = None
        extra["corrected"] = True

    return state
