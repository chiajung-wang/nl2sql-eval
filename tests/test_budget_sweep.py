"""Step-6 follow-up (#75): the budget-crossover harness's pure logic.

Exercises the offline pieces of ``eval.eval_bird_budget`` — the
RAG-over-truncate gap and the divergence-based convergence detection — without
any LLM call or BIRD download, by assembling :class:`BatchReport`s from canned
results. The paid sweep itself just feeds these the real per-budget reports.
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


def _point(budget: int, naive_nc: int, rag_nc: int, divergence: float) -> BudgetPoint:
    return BudgetPoint(
        budget=budget,
        naive=_report(naive_nc, 10),
        rag=_report(rag_nc, 10),
        divergence=divergence,
    )


def test_budget_point_gap_is_rag_minus_naive():
    assert _point(256, 5, 8, 0.5).gap == approx(0.3)


def test_convergence_is_smallest_zero_divergence_budget_not_gap_crossing():
    # The gap stays POSITIVE at 1024 (8 vs 7) yet divergence hits 0 there — both
    # modes send identical prompts, so the residual gap is noise, not a crossover.
    # Convergence must key off divergence, not the gap.
    points = [
        _point(256, 4, 7, 0.75),
        _point(512, 6, 7, 0.50),
        _point(1024, 7, 8, 0.0),  # gap +0.1 but identical selections → converged
    ]
    assert convergence_budget(points) == 1024


def test_convergence_none_when_no_budget_reaches_zero_divergence():
    points = [_point(256, 4, 7, 0.75), _point(512, 5, 7, 0.40)]
    assert convergence_budget(points) is None


def test_convergence_picks_lowest_zero_divergence_budget_regardless_of_order():
    points = [
        _point(1024, 7, 7, 0.0),
        _point(256, 4, 7, 0.75),
        _point(512, 7, 7, 0.0),  # earliest zero-divergence budget
    ]
    assert convergence_budget(points) == 512
