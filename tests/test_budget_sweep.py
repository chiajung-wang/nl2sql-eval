"""Step-6 follow-up (#75): the budget-crossover harness's pure logic.

Exercises the offline pieces of ``eval.eval_bird_budget`` — the
RAG-over-truncate gap and the convergence-budget detection — without any LLM
call or BIRD download, by assembling :class:`BatchReport`s from canned results.
The paid sweep itself just feeds these the real per-budget reports.
"""

from __future__ import annotations

from pytest import approx

from eval.eval_bird_budget import BudgetPoint, convergence_budget
from eval.metrics import BatchReport, CaseResult
from nl2sql.pipeline.state import TerminalState


def _report(n_correct: int, total: int, *, recall: float | None = None) -> BatchReport:
    """A BatchReport with ``n_correct`` of ``total`` cases marked correct."""
    results = tuple(
        CaseResult(
            case_id=str(i),
            db_id="db",
            terminal_state=(
                TerminalState.SUCCESS if i < n_correct else TerminalState.WRONG_ANSWER
            ),
            correct=i < n_correct,
            retrieval_recall=recall,
        )
        for i in range(total)
    )
    return BatchReport(results)


def test_budget_point_gap_is_rag_minus_naive():
    point = BudgetPoint(budget=256, naive=_report(5, 10), rag=_report(8, 10))
    assert point.gap == approx(0.3)


def test_convergence_budget_is_smallest_budget_where_naive_catches_up():
    # Tight budget: RAG leads. Generous budget: the schema fits, gap closes.
    points = [
        BudgetPoint(budget=256, naive=_report(4, 10), rag=_report(7, 10)),
        BudgetPoint(budget=512, naive=_report(6, 10), rag=_report(7, 10)),
        BudgetPoint(budget=1024, naive=_report(7, 10), rag=_report(7, 10)),  # gap 0
    ]
    assert convergence_budget(points) == 1024


def test_convergence_budget_none_when_rag_leads_throughout():
    points = [
        BudgetPoint(budget=256, naive=_report(4, 10), rag=_report(7, 10)),
        BudgetPoint(budget=512, naive=_report(5, 10), rag=_report(7, 10)),
    ]
    assert convergence_budget(points) is None


def test_convergence_picks_lowest_qualifying_budget_regardless_of_input_order():
    # Out-of-order input: convergence must still be the smallest budget with gap≤0.
    points = [
        BudgetPoint(budget=1024, naive=_report(7, 10), rag=_report(7, 10)),
        BudgetPoint(budget=256, naive=_report(4, 10), rag=_report(7, 10)),
        BudgetPoint(budget=512, naive=_report(7, 10), rag=_report(7, 10)),
    ]
    assert convergence_budget(points) == 512
