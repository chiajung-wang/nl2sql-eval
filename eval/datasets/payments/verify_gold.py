"""Verify the payments gold answers by executing each gold_sql against the seed.

This is the reproducible backing for the ``machine_verified`` flag in
``questions.json``: it runs every question's ``gold_sql`` against a live, seeded
payments db and asserts the rows match the stored ``gold_result`` exactly
(column names + ordered rows). It does NOT touch the ``human_reviewed`` flag —
that sign-off is the reviewer's, not this script's.

Run against a live Postgres (see docker-compose.yml at the repo root):

    docker compose up -d
    uv run python -m eval.datasets.payments.load        # apply DDL + seed
    uv run python -m eval.datasets.payments.verify_gold

Connection comes from ``PAYMENTS_DB_URL`` (same as load.py). Exits non-zero if
any gold answer fails to reproduce, so it doubles as a check you can wire into a
db-backed CI job. Comparison here is exact (the gold_sql carries its own
ORDER BY); the harness's canonicalized comparator lands separately in Step 2.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from eval.datasets.payments.load import get_engine
from eval.datasets.payments.questions import load_questions


def _normalize(value: Any) -> Any:
    """Coerce driver types to the JSON-storable forms used in gold_result.

    Postgres returns SUM()/numeric as ``Decimal``; the stored gold uses plain
    ints (cents) / floats. Everything else passes through unchanged.
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def check_question(engine: Engine, question: dict[str, Any]) -> list[str]:
    """Run one gold_sql and return a list of mismatch messages (empty == pass)."""
    with engine.connect() as conn:
        result = conn.execute(text(question["gold_sql"]))
        got_columns = list(result.keys())
        got_rows = [[_normalize(v) for v in row] for row in result.all()]

    expected = question["gold_result"]
    problems: list[str] = []
    if got_columns != expected["columns"]:
        problems.append(f"columns {got_columns} != gold {expected['columns']}")
    if got_rows != expected["rows"]:
        problems.append(f"rows {got_rows} != gold {expected['rows']}")
    return problems


def main() -> int:
    engine = get_engine()
    print(f"Verifying gold against {engine.url.render_as_string(hide_password=True)}\n")

    questions = load_questions()
    failures = 0
    for question in questions:
        problems = check_question(engine, question)
        if problems:
            failures += 1
            print(f"  MISMATCH {question['id']}")
            for problem in problems:
                print(f"      {problem}")
        else:
            print(f"  OK       {question['id']}")

    total = len(questions)
    print(f"\n{total - failures}/{total} gold answers reproduced.")
    if failures:
        print("FAIL: gold no longer matches the seed — fix gold_sql/gold_result/seed.")
        return 1
    print("PASS: every gold_sql reproduces its stored gold_result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
