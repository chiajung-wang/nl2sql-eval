"""Step 6, Issue 5 — the large-schema slice floor and the retrieval-lift row.

Pure/deterministic: the ``min_tables`` floor selects exactly the large-schema dbs
(disjoint from the Step-3 small-schema ceiling), and the lift row formats the
naive→RAG accuracy delta. No BIRD download, no API.
"""

from __future__ import annotations

from eval.datasets.bird.slice import select_slice
from eval.eval_bird_rag import lift_row
from eval.metrics import BatchReport, CaseResult
from nl2sql.pipeline.state import TerminalState

_SMALL = "small_db"
_BIG = "big_db"
_TABLE_COUNTS = {_SMALL: 2, _BIG: 20}


def _questions() -> list[dict]:
    qs: list[dict] = []
    qid = 0
    for db, base in ((_SMALL, 0), (_BIG, 100)):
        for difficulty in ("simple", "moderate", "challenging"):
            for _ in range(10):
                qs.append(
                    {"question_id": base + qid, "db_id": db, "difficulty": difficulty}
                )
                qid += 1
    return qs


# --- the min_tables floor (large-schema selection) -------------------------


def test_min_tables_floor_selects_only_large_schema_dbs():
    ids = select_slice(
        _questions(), _TABLE_COUNTS, min_tables=6, max_tables=10_000, n=12, seed=1
    )
    by_id = {q["question_id"]: q for q in _questions()}
    assert ids and all(by_id[i]["db_id"] == _BIG for i in ids)


def test_step3_ceiling_and_step6_floor_are_disjoint():
    qs = _questions()
    small = set(select_slice(qs, _TABLE_COUNTS, max_tables=5, n=999, seed=1))
    large = set(
        select_slice(qs, _TABLE_COUNTS, min_tables=6, max_tables=10_000, n=999, seed=1)
    )
    assert small and large
    assert small.isdisjoint(large)  # disjoint by schema size — no question in both


def test_large_slice_is_seeded_and_deterministic():
    args = (_questions(), _TABLE_COUNTS)
    a = select_slice(*args, min_tables=6, max_tables=10_000, n=12, seed=7)
    b = select_slice(*args, min_tables=6, max_tables=10_000, n=12, seed=7)
    c = select_slice(*args, min_tables=6, max_tables=10_000, n=12, seed=8)
    assert a == b and a != c


# --- the retrieval-lift RESULTS row ----------------------------------------


def _report(n_correct: int, total: int) -> BatchReport:
    results = tuple(
        CaseResult(
            case_id=str(i),
            db_id="bird",
            terminal_state=TerminalState.SUCCESS
            if i < n_correct
            else TerminalState.WRONG_ANSWER,
            correct=i < n_correct,
        )
        for i in range(total)
    )
    return BatchReport(results)


def test_lift_row_formats_naive_to_rag_delta():
    naive = _report(8, 40)  # 0.200
    rag = _report(18, 40)  # 0.450
    row = lift_row(
        naive,
        rag,
        model="claude-sonnet-4-6",
        prompt_version="generate/v3",
        commit="abc1234",
    )
    assert "| 6 | retrieval lift (pass@1) |" in row
    assert "0.200 (8/40) → 0.450 (18/40) [lift +0.250]" in row
    assert "claude-sonnet-4-6" in row and "abc1234" in row


def test_lift_row_handles_zero_and_negative_lift():
    same = lift_row(
        _report(10, 40), _report(10, 40), model="m", prompt_version="p", commit="c"
    )
    assert "[lift +0.000]" in same
    worse = lift_row(
        _report(12, 40), _report(8, 40), model="m", prompt_version="p", commit="c"
    )
    assert "[lift -0.100]" in worse
