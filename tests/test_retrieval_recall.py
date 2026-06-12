"""Proof of the retrieval-recall metric (Step 6, Issue 3).

Retrieval recall measures the *silent* wrong-schema failure — valid SQL over the
wrong tables, no error — which accuracy alone can't see. The gold-table set is
extracted deterministically from the AST (never a string scan), and recall is
reported alongside accuracy, excluding the cases where it is undefined.
"""

from __future__ import annotations

from eval.harness import Case, run_batch
from eval.metrics import (
    BatchReport,
    CaseResult,
    gold_query_tables,
    retrieval_recall,
    summary_lines,
)
from nl2sql.pipeline.state import RunState

# --- gold-table extraction (deterministic, AST-based) ----------------------


def test_gold_tables_from_simple_query():
    assert gold_query_tables("SELECT name FROM users") == {"users"}


def test_gold_tables_dedupes_and_casefolds():
    assert gold_query_tables("SELECT * FROM Users u JOIN USERS v ON u.id = v.id") == {
        "users"
    }


def test_gold_tables_across_joins_and_subqueries():
    sql = (
        "SELECT t.element FROM atom AS T1 "
        "JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id "
        "WHERE T2.molecule_id IN (SELECT molecule_id FROM bond)"
    )
    assert gold_query_tables(sql) == {"atom", "molecule", "bond"}


def test_gold_tables_not_fooled_by_aliases_or_string_literals():
    # An alias named like a table, and the word FROM inside a string, must not
    # register as tables — this is why extraction is AST-based, not a scan.
    sql = "SELECT 'from orders' AS note FROM users AS orders"
    assert gold_query_tables(sql) == {"users"}


def test_gold_tables_empty_when_no_table():
    assert gold_query_tables("SELECT 1") == set()


# --- recall = |retrieved ∩ gold| / |gold| ----------------------------------


def test_recall_none_when_retrieval_did_not_run():
    assert retrieval_recall(None, "SELECT * FROM users") is None


def test_recall_none_when_gold_has_no_tables():
    assert retrieval_recall(["users"], "SELECT 1") is None


def test_recall_full_partial_and_case_insensitive():
    gold = "SELECT * FROM atom JOIN molecule ON atom.mid = molecule.mid"
    assert retrieval_recall(["atom", "molecule"], gold) == 1.0
    assert retrieval_recall(["ATOM"], gold) == 0.5  # one of two, case-insensitive
    assert retrieval_recall(["unrelated"], gold) == 0.0


def test_recall_ignores_extra_retrieved_tables():
    # Recall is about coverage of the gold tables, not precision — extra tables
    # retrieved don't lower it (they may raise prompt cost, a separate axis).
    gold = "SELECT * FROM atom"
    assert retrieval_recall(["atom", "bond", "molecule"], gold) == 1.0


# --- aggregation ------------------------------------------------------------


def _result(recall: float | None) -> CaseResult:
    from nl2sql.pipeline.state import TerminalState

    return CaseResult(
        case_id="c",
        db_id="bird",
        terminal_state=TerminalState.SUCCESS,
        correct=True,
        retrieval_recall=recall,
    )


def test_mean_recall_excludes_undefined_cases():
    report = BatchReport((_result(1.0), _result(0.5), _result(None)))
    assert report.n_with_recall == 2
    assert report.mean_retrieval_recall == 0.75  # (1.0 + 0.5) / 2, None excluded


def test_mean_recall_is_none_when_no_case_has_it():
    report = BatchReport((_result(None), _result(None)))
    assert report.mean_retrieval_recall is None
    # And the summary line is omitted entirely on the naive-dump path.
    assert not any("retrieval recall" in line for line in summary_lines(report))


def test_summary_includes_recall_line_when_present():
    report = BatchReport((_result(1.0), _result(0.5)))
    assert any("retrieval recall: 0.750" in line for line in summary_lines(report))


# --- harness wiring ---------------------------------------------------------


def _state(retrieved: list[str] | None) -> RunState:
    s = RunState(question="q", db_id="bird")
    s.candidate_sql = "SELECT * FROM atom"
    s.result_columns = ["x"]
    s.result_rows = [(1,)]
    s.retrieved_tables = retrieved
    return s


def _case(gold_sql: str) -> Case:
    return Case(
        id="c",
        question="q",
        db_id="bird",
        gold_sql=gold_sql,
        gold_result={"columns": ["x"], "rows": [[1]]},
    )


def test_run_batch_populates_recall_from_state():
    gold = "SELECT element FROM atom JOIN molecule ON atom.mid = molecule.mid"
    states: dict[str, RunState] = {
        "hit": _state(["atom", "molecule"]),
        "miss": _state(["atom"]),
    }
    cases = [
        Case(
            id="hit",
            question="q",
            db_id="bird",
            gold_sql=gold,
            gold_result={"columns": ["x"], "rows": [[1]]},
        ),
        Case(
            id="miss",
            question="q",
            db_id="bird",
            gold_sql=gold,
            gold_result={"columns": ["x"], "rows": [[1]]},
        ),
    ]
    report = run_batch(cases, lambda c: states[c.id])
    by_id = {r.case_id: r for r in report.results}
    assert by_id["hit"].retrieval_recall == 1.0
    assert by_id["miss"].retrieval_recall == 0.5


def test_run_batch_recall_none_on_naive_dump_path():
    report = run_batch([_case("SELECT * FROM atom")], lambda c: _state(None))
    assert report.results[0].retrieval_recall is None
