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
    starts clean. Only a ``corrected`` flag is attached to the obs span — never
    the error text or row values, which never reach a failed run anyway. Mutates
    and returns ``state``.

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


def correct_soundness(state: RunState) -> RunState:
    """Stage a soundness flag as a correction signal, then clear it for a retry.

    A soundness hit (Step 12, #139) is *not* an execution error — the candidate ran
    (or would run) fine, it is just a likely-wrong construction. It reuses the same
    ``state.correction`` feedback channel the next ``generate`` renders (correct.py
    is the natural home for the paper's "flag → ask for a fix" loop), carrying the
    check's reason so the model sees *why* to rewrite. Clears the flag so a stale
    verdict can't survive into the next cycle. A no-op when nothing is flagged, so a
    stray call cannot fabricate a correction.
    """
    with stage_span("correct", db_id=state.db_id, attempt=state.attempts) as extra:
        if not state.soundness_flag:
            extra["corrected"] = False
            return state

        state.correction = {
            "sql": state.candidate_sql or "",
            "error": state.soundness_reason or "likely-wrong SQL construction",
        }
        state.soundness_flag = False
        state.soundness_reason = None
        state.soundness_rule = None
        extra["corrected"] = True

    return state


def correct_literal(state: RunState) -> RunState:
    """Stage a literal-steering flag as a correction signal, then clear it.

    A literal_check hit (Step 12, #141) is the "right value, wrong column" case — the
    candidate would run, but constrains a literal against a column that doesn't hold
    it. Reuses the same ``state.correction`` channel the next ``generate`` renders,
    carrying the steering message (which columns *do* hold the value) so the model can
    flip to the right field — exactly the paper's ``County Name`` → ``District`` fix.
    A no-op when nothing is flagged, so a stray call cannot fabricate a correction.
    """
    with stage_span("correct", db_id=state.db_id, attempt=state.attempts) as extra:
        if not state.literal_flag:
            extra["corrected"] = False
            return state

        state.correction = {
            "sql": state.candidate_sql or "",
            "error": state.literal_reason
            or "a literal is constrained on the wrong column",
        }
        state.literal_flag = False
        state.literal_reason = None
        extra["corrected"] = True

    return state
