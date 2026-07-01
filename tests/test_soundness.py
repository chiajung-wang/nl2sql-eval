"""Proof of the deterministic soundness (bad-construction) checks (Step 12, #139).

Source: Shkapenyuk et al., arXiv:2505.19988v2 §4. Mirrors how the guard is
proven, in three layers:

1. **Fixture-driven** — every ``(candidate SQL, expected verdict)`` case under
   ``fixtures/soundness/`` is replayed through ``check_soundness_sql``; adding a
   case is exercised automatically (CLAUDE.md §8, §11).
2. **Measurement** — the **catch rate** (over the ``flag`` cases) and the
   **false-positive rate** (over the ``pass`` cases) are computed from the fixture
   and asserted; these are the primary deliverable, reported in ``RESULTS.md``.
3. **Wiring** — soundness runs after a guard-allow in the import-shared pipeline
   as a *correction signal*: a flag with budget left feeds back and regenerates; a
   flag with the budget spent executes anyway (a soundness heuristic never loses a
   run). All offline with a fake generator — no network, no key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from nl2sql.pipeline.correct import correct_soundness
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.soundness import check_soundness_sql
from nl2sql.pipeline.state import RunState
from nl2sql.schema_index import build_schema_index
from tests.test_pipeline_loop import FakeLLMClient

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "soundness"


def _load_cases() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(_FIXTURE_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        for case in data["cases"]:
            case["_file"] = path.stem
            cases.append(case)
    return cases


SOUNDNESS_CASES = _load_cases()


# --- 1. fixture-driven proof ----------------------------------------------


def test_fixture_is_non_empty():
    # Guards against a glob/parse regression silently turning the proof into a
    # no-op (zero cases would vacuously "pass").
    assert SOUNDNESS_CASES, "no soundness cases loaded — fixture missing/unparseable"


@pytest.mark.parametrize(
    "case", [pytest.param(c, id=f"{c['_file']}:{c['id']}") for c in SOUNDNESS_CASES]
)
def test_soundness_fixture_verdicts(case):
    result = check_soundness_sql(case["sql"], dialect=case.get("dialect", "SQLite"))
    verdict = "flag" if result.rejected else "pass"
    assert verdict == case["expected_verdict"], (
        f"{case['id']}: got {verdict}/{result.rule}"
    )
    if case["expected_verdict"] == "flag":
        assert result.rule == case["expected_rule"], (
            f"{case['id']}: fired '{result.rule}', expected '{case['expected_rule']}'"
        )


# --- 2. measurement: catch rate + false-positive rate ---------------------


def test_catch_rate_and_false_positive_rate():
    """The primary deliverable (PRD rule 11): the fixture catch rate and FP rate.

    Catch rate = flagged / (queries that should flag); FP rate = wrongly-flagged /
    (queries that should pass). On this curated fixture the checks are exact — a
    perfect catch with zero false positives — so a regression that makes a check
    over- or under-fire trips this assertion, and the printed rates are the numbers
    that land in RESULTS.md.
    """
    flag_cases = [c for c in SOUNDNESS_CASES if c["expected_verdict"] == "flag"]
    pass_cases = [c for c in SOUNDNESS_CASES if c["expected_verdict"] == "pass"]
    assert flag_cases and pass_cases  # both sets are represented

    caught = sum(
        check_soundness_sql(c["sql"], dialect=c.get("dialect", "SQLite")).rejected
        for c in flag_cases
    )
    false_pos = sum(
        check_soundness_sql(c["sql"], dialect=c.get("dialect", "SQLite")).rejected
        for c in pass_cases
    )
    catch_rate = caught / len(flag_cases)
    fp_rate = false_pos / len(pass_cases)
    print(
        f"\nsoundness fixture: "
        f"catch_rate={catch_rate:.3f} ({caught}/{len(flag_cases)}) "
        f"false_positive_rate={fp_rate:.3f} ({false_pos}/{len(pass_cases)})"
    )
    assert catch_rate == 1.0
    assert fp_rate == 0.0


# --- 3. unit contract of check_soundness_sql ------------------------------


def test_no_sql_is_allowed():
    # Nothing to construct badly — not a soundness concern (like the guard).
    assert check_soundness_sql(None).allowed
    assert check_soundness_sql("   ").allowed


def test_unparseable_sql_allows_through():
    # Parse-safety is the guard's job (already run upstream); soundness never fails
    # a run on a parse it cannot make.
    assert check_soundness_sql("this is not sql at all").allowed


def test_min_hazard_is_ast_not_string_match():
    # A column literally named "minimum" must not trip the min() check — AST, not a
    # keyword scan (CLAUDE.md §4).
    sql = "SELECT minimum FROM t WHERE minimum IS NOT NULL"
    assert check_soundness_sql(sql).allowed


def test_max_and_desc_are_not_flagged():
    # NULLs sort last for max / descending order, so neither is a hazard.
    assert check_soundness_sql("SELECT MAX(x) FROM t").allowed
    assert check_soundness_sql("SELECT a FROM t ORDER BY x DESC LIMIT 1").allowed


def test_correlated_minmax_subquery_is_not_flagged():
    sql = (
        "SELECT name FROM products p WHERE p.price = "
        "(SELECT MIN(p2.price) FROM products p2 WHERE p2.category = p.category)"
    )
    assert check_soundness_sql(sql).allowed


# --- 4. correct_soundness contract ----------------------------------------


def test_correct_soundness_stages_feedback_when_flagged():
    state = RunState(question="q", db_id="db")
    state.candidate_sql = "SELECT MIN(price) FROM products"
    state.soundness_flag = True
    state.soundness_reason = "null_ordering: min(price) without a NOT NULL guard"
    correct_soundness(state)
    assert state.correction == {
        "sql": "SELECT MIN(price) FROM products",
        "error": "null_ordering: min(price) without a NOT NULL guard",
    }
    assert state.soundness_flag is False  # cleared for the retry


def test_correct_soundness_is_noop_when_unflagged():
    state = RunState(question="q", db_id="db")
    correct_soundness(state)
    assert state.correction is None  # a stray call cannot fabricate a correction


# --- 5. graph wiring: soundness as a correction signal --------------------


@pytest.fixture
def store_engine():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE products (id INTEGER PRIMARY KEY, price INTEGER)")
        )
        conn.execute(text("INSERT INTO products VALUES (1, 10), (2, 20)"))
    return engine


def test_flagged_candidate_feeds_back_and_regenerates(store_engine):
    index = build_schema_index(store_engine)
    # First candidate trips null_ordering; the second is guarded and clean.
    client = FakeLLMClient(
        [
            "SELECT MIN(price) FROM products",
            "SELECT MIN(price) FROM products WHERE price IS NOT NULL",
        ]
    )
    state = run_pipeline(
        "cheapest product",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        max_attempts=3,
    )
    assert len(client.calls) == 2  # regenerated once on the soundness flag
    assert state.soundness_flag is False  # the retry cleared it
    assert state.error is None
    assert state.result_rows == [(10,)]  # the clean candidate ran


def test_flagged_candidate_executes_when_budget_spent(store_engine):
    index = build_schema_index(store_engine)
    # Every candidate is flagged; with the budget spent the run must still execute
    # it — a soundness heuristic never loses a run.
    client = FakeLLMClient(["SELECT MIN(price) FROM products"])
    state = run_pipeline(
        "cheapest product",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        max_attempts=2,
    )
    assert len(client.calls) == 2  # one feed-back retry, then budget spent
    assert state.soundness_flag is True  # still flagged, but not lost
    assert state.result_rows == [(10,)]  # executed anyway


def test_single_shot_flagged_candidate_executes_without_retry(store_engine):
    index = build_schema_index(store_engine)
    client = FakeLLMClient(["SELECT MIN(price) FROM products"])
    state = run_pipeline(
        "cheapest product",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        max_attempts=1,
    )
    # pass@1: no correction budget, so a soundness flag never retries.
    assert len(client.calls) == 1
    assert state.result_rows == [(10,)]


def test_clean_candidate_path_is_unaffected(store_engine):
    index = build_schema_index(store_engine)
    client = FakeLLMClient(["SELECT price FROM products WHERE id = 1"])
    state = run_pipeline(
        "price of product 1",
        schema_index=index,
        engine=store_engine,
        db_id="store",
        dialect="SQLite",
        client=client,
        max_attempts=3,
    )
    assert len(client.calls) == 1  # no soundness flag → straight to execute
    assert state.soundness_flag is False
    assert state.result_rows == [(10,)]
