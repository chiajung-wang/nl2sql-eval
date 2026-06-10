"""Structural guard for the verified payments question set (Issue 3).

CI-safe: validates the dataset's invariants without a live database. The gold
*answers* are verified by execution against the seed at authoring time (recorded
in ``questions.json`` ``_meta.verification``); these tests protect the file's
shape, uniqueness, and self-consistency so it stays loadable by the harness.
"""

import re

import pytest

from eval.datasets.payments.questions import load_meta, load_questions

# Base tables defined in schema.sql — gold_tables must reference only these.
SCHEMA_TABLES = {
    "users",
    "merchants",
    "payment_methods",
    "transactions",
    "refunds",
    "disputes",
    "ledger",
}

QUESTIONS = load_questions()
REQUIRED_FIELDS = {
    "id",
    "question",
    "difficulty",
    "category",
    "gold_sql",
    "gold_tables",
    "gold_result",
    "machine_verified",
    "human_reviewed",
}


def test_question_set_size_in_range() -> None:
    # Issue 3 calls for a small, high-trust set of roughly 5–10 pairs.
    assert 5 <= len(QUESTIONS) <= 12


def test_ids_are_unique() -> None:
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_question_record_well_formed(q: dict) -> None:
    assert REQUIRED_FIELDS <= q.keys()
    assert re.fullmatch(r"pay-\d{3}", q["id"])
    assert q["question"].strip()
    assert q["gold_sql"].strip().endswith(";")
    assert q["difficulty"] in {"easy", "medium", "hard"}


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_gold_tables_exist_in_schema(q: dict) -> None:
    assert q["gold_tables"], "gold_tables must be non-empty (retrieval-recall ground)"
    assert set(q["gold_tables"]) <= SCHEMA_TABLES


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_gold_result_shape_consistent(q: dict) -> None:
    result = q["gold_result"]
    columns = result["columns"]
    assert columns, "gold_result must declare its columns"
    for row in result["rows"]:
        assert len(row) == len(columns), f"{q['id']}: row width != column count"


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_every_gold_answer_is_machine_verified(q: dict) -> None:
    # The agent stands behind this: gold_sql reproduces gold_result against the
    # seed. Verified by execution at authoring time (see _meta.verification).
    assert q["machine_verified"] is True


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_human_review_flag_is_a_boolean_signoff(q: dict) -> None:
    # The AFK agent never self-ticks this; a human flips it to true after
    # eyeballing question intent + gold against the seeded rows. We only assert
    # it is present and boolean — its value is the human's to set.
    assert isinstance(q["human_reviewed"], bool)


def test_set_spans_lookup_join_and_aggregation() -> None:
    categories = {q["category"] for q in QUESTIONS}
    assert "lookup" in categories
    assert {"join", "join_aggregation"} & categories, "need at least one join"
    assert {"aggregation", "join_aggregation"} & categories, "need an aggregation"


def test_meta_marks_dataset_machine_verified() -> None:
    meta = load_meta()
    assert meta["machine_verified"] is True
    assert isinstance(meta["human_reviewed"], bool)
