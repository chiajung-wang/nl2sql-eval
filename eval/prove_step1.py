"""Step 1 end-to-end proof (issue 5): one seed question, generate→execute→return.

This is the Step-1 Definition-of-Done slice — proof that the machine runs end to
end. It takes a hand-verified payments question from the Issue 3 seed set, runs
it through the *import-shared* pipeline (``graph.run_pipeline`` — the same loop
the harness and demo use), classifies the terminal state via the harness
classifier, and asserts the returned result reproduces the question's verified
gold answer.

Needs a live, seeded Postgres and ``ANTHROPIC_API_KEY``:

    docker compose up -d
    uv run python -m eval.datasets.payments.load
    uv run python -m eval.prove_step1            # defaults to pay-001
    uv run python -m eval.prove_step1 pay-004    # any seed question id

The gold check here is a value-level row match (column aliases ignored — two
equally-correct queries can label the same value differently). It is a
deliberate Step-1 stand-in; the canonicalized result-set comparator with
order-insensitivity lands in ``eval/compare.py`` at Step 2. ``RESULTS.md``
discipline starts at Step 3, so this prints PASS/FAIL but writes no log entry.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from eval.datasets.payments.questions import load_questions

# Reuse the gold-verification normalizer so driver-type coercion (Postgres
# returns Decimal for SUM(); gold stores plain int cents) has a single source.
# TODO(step-2): this is a private symbol from another package — promote the
# shared coercion to a public home (e.g. eval/compare.py's canonicalization)
# when the comparator lands, rather than reaching across into ``_normalize``.
from eval.datasets.payments.verify_gold import _normalize
from eval.harness import classify_terminal_state
from nl2sql.pipeline.execute import get_engine
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState, TerminalState

SCHEMA_SQL = Path(__file__).resolve().parent / "datasets/payments/schema.sql"


def _find_question(question_id: str) -> dict[str, Any]:
    for question in load_questions():
        if question["id"] == question_id:
            return question
    known = ", ".join(q["id"] for q in load_questions())
    raise SystemExit(f"unknown question id {question_id!r}; choose one of: {known}")


def gold_matches(state: RunState, gold: dict[str, Any]) -> bool:
    """Value-level match of the pipeline result against the stored gold.

    Compares the result-set *values* row-for-row and ignores column aliases: a
    different label for the same value is still correct (CLAUDE.md domain rule 1
    — two different queries can be equally correct; never string-match). Cells
    are normalized the same way the gold-verification script does.

    Step-1 stand-in only. The canonicalized comparator that also adds
    order-insensitivity for unordered queries and fuller type canonicalization
    is ``eval/compare.py`` at Step 2.

    Reads ``state.result_rows`` directly, which is the *raw verified result* —
    correct, but only because the pipeline has no ``redact`` stage yet. CLAUDE.md
    §3/§5.2 require scoring upstream of redaction; once ``redact`` lands the two
    exits split and this must score the raw exit, never the presented one.
    TODO(step-2): score the explicit raw-result exit, not ``state.result_rows``.
    """
    expected_rows = gold["gold_result"]["rows"]
    got_rows = [[_normalize(v) for v in row] for row in (state.result_rows or [])]
    return got_rows == expected_rows


def prove(question_id: str) -> int:
    """Run one seed question end to end; return a process exit code (0 == proven)."""
    gold = _find_question(question_id)
    schema = SCHEMA_SQL.read_text()

    state = run_pipeline(gold["question"], schema=schema, engine=get_engine())
    terminal = classify_terminal_state(state)

    print(f"\n[{gold['id']}] {gold['question']}")
    print(f"SQL:      {state.candidate_sql}")
    if state.error:
        print(f"ERROR:    {state.error}")
    else:
        print(f"columns:  {state.result_columns}")
        print(f"rows:     {state.result_rows}")
    print(f"terminal: {terminal}")

    if terminal is TerminalState.EXECUTION_ERROR_FINAL:
        print("FAIL: execution failed — bucketed as execution_error_final.")
        return 1

    # Terminal SUCCESS means the run executed cleanly; correctness against gold is
    # the separate Step-1 assertion below (WRONG_ANSWER needs the Step-2
    # comparator before it is a reachable terminal state).
    if gold_matches(state, gold):
        print("PASS: result reproduces the verified gold answer (terminal success).")
        return 0

    print("FAIL: ran cleanly (terminal success) but result does NOT match gold.")
    print(f"      gold columns: {gold['gold_result']['columns']}")
    print(f"      gold rows:    {gold['gold_result']['rows']}")
    return 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    question_id = sys.argv[1] if len(sys.argv) > 1 else "pay-001"
    return prove(question_id)


if __name__ == "__main__":
    raise SystemExit(main())
