"""Batch-evaluate the payments verified gold set through the shared pipeline.

The Step-3 harness proven on **trusted ground** before it is ever pointed at
BIRD: if it can't score questions whose answers we know cold, it has no business
scoring questions we don't. Loads ``.env``, builds the seeded-Postgres engine and
the payments schema, maps each verified question to a :class:`~eval.harness.Case`,
runs the batch through the **import-shared** pipeline + Step-2 comparator, and
prints pass@1 and the terminal-state mix.

No ``RESULTS.md`` entry — that begins with the frozen BIRD slice (Issue 3); this
is the harness's self-check, not a benchmark number.

    docker compose up -d
    uv run python -m eval.datasets.payments.load
    uv run python -m eval.eval_payments
"""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

from eval.datasets.payments.questions import load_questions
from eval.harness import Case, run_batch
from eval.metrics import BatchReport
from nl2sql.pipeline.execute import get_engine
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState

SCHEMA_SQL = Path(__file__).resolve().parent / "datasets/payments/schema.sql"


def build_payments_cases() -> list[Case]:
    """Map each verified payments question to a harness :class:`Case`."""
    return [
        Case(
            id=q["id"],
            question=q["question"],
            db_id="payments",
            gold_sql=q["gold_sql"],
            gold_result=q["gold_result"],
            difficulty=q.get("difficulty"),
        )
        for q in load_questions()
    ]


def _print_report(report: BatchReport) -> None:
    print(f"\npass@1: {report.pass_at_1:.3f}  ({report.n_correct}/{report.total})")
    print("terminal states:")
    for state, count in report.terminal_counts().items():
        if count:
            print(f"  {state.value:24} {count}")
    print("pass@1 by difficulty:")
    for difficulty, rate in sorted(report.pass_at_1_by("difficulty").items(), key=str):
        print(f"  {str(difficulty):24} {rate:.3f}")
    print("\nper-case:")
    for r in report.results:
        mark = "PASS" if r.correct else r.terminal_state.value
        print(f"  [{r.case_id}] {mark:22} {r.note or ''}")


def main() -> int:
    """Run the payments batch and print pass@1; returns a process exit code."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    schema = SCHEMA_SQL.read_text()
    engine = get_engine()
    cases = build_payments_cases()

    def run_one(case: Case) -> RunState:
        return run_pipeline(
            case.question, schema=schema, engine=engine, db_id=case.db_id
        )

    report = run_batch(cases, run_one)
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
