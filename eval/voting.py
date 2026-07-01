"""Result-set majority voting for candidate selection (Step 12, #142).

Source: Shkapenyuk et al., arXiv:2505.19988v2 §4 — their submission generates
several candidates and selects one by **majority vote on executed result-sets**.
The key reuse: **our comparator (``eval/compare.py``) *is* the result-set
equivalence that vote needs** — including BIRD set-semantics. Voting is the proven
comparator applied to *candidate selection* instead of *gold scoring*; we do not
rebuild any SQL-equivalence logic, and there is no string-match and no LLM judge
(CLAUDE.md §7).

**Scoring boundary (CLAUDE.md §3/§5).** Voting only *selects* a candidate; it does
not change what or where the harness scores. The harness still scores the selected
candidate's **raw verified result** against gold, upstream of redaction — this
module returns the chosen candidate/index, never a score.

The selector here is a pure function both the harness and the demo can share
(import-shared, no drift). The k-candidate *generation* loop that feeds it — run the
pipeline against a :func:`~eval.candidate_diversity.shuffle_field_order` variant per
candidate, plus a varied live seed — lands with the deferred live twin, since it
needs live diverse generation.

Determinism (§9 repeatability): candidates are grouped into result-set equivalence
classes; the largest class wins; a tie (or no majority) is broken **deterministically
by earliest candidate index**, not randomly (the paper picks randomly — we prefer a
reproducible tiebreak). Errored candidates carry no votable result and are excluded;
if *every* candidate errored, the first is returned so a run is never lost.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from eval.compare import ResultLike, compare
from nl2sql.pipeline.state import RunState


@dataclass(frozen=True)
class Candidate:
    """One executed candidate: its result-set, its SQL, and whether it errored.

    ``result`` is the ``{"columns", "rows"}`` mapping the comparator consumes — the
    **raw verified result** (voting never sees redacted rows). ``errored`` marks a
    candidate with no votable result (execution failed / never ran); it is excluded.
    An **empty** result set is *not* errored — it is a valid, votable distinct result
    (the comparator treats two empty sets as equivalent)."""

    result: ResultLike
    sql: str | None = None
    errored: bool = False


@dataclass(frozen=True)
class VoteOutcome:
    """The selection plus the diagnostics that explain the pass@1→pass@k gap.

    ``agreement`` is the size of the winning equivalence class (e.g. 2 of 3);
    ``n_votable`` is how many candidates were votable (non-errored) — the majority
    denominator; ``n_groups`` is how many distinct result-sets they produced (1 =
    unanimous, k = all different); ``tie`` is whether the deterministic earliest-index
    tiebreak decided it (two classes of equal, largest size). A strong generator whose
    candidates agree shows ``agreement == n_votable`` and ``n_groups == 1`` — the vote
    was a no-op, exactly the honest null Step 5 taught to expect.
    """

    selected_index: int
    agreement: int
    n_candidates: int
    n_votable: int
    n_groups: int
    tie: bool


# A syntactically valid gold-SQL sentinel with no ``ORDER BY`` — no gold query
# exists at selection time, and this parses cleanly (unlike ``""``, which the
# comparator would log a parse warning for) to "order not significant", so the
# order-insensitive **set** rules apply (the paper "converts results to sets").
_NO_GOLD_SENTINEL = "SELECT 1"


def _equivalent(a: ResultLike, b: ResultLike) -> bool:
    """Whether two candidate result-sets are equivalent, via the comparator.

    Grouping treats ``compare`` as a **symmetric** relation (candidate vs candidate,
    neither is gold). That holds under the default canonicalization: the set / order-
    insensitive / value-normalization rules make ``a≡b`` iff ``b≡a``. A future
    *asymmetric* rule (one-sided tolerance) would need a symmetric wrapper here; the
    reuse is intentionally read-only and doesn't touch the comparator's verdict logic.
    """
    return compare(a, b, _NO_GOLD_SENTINEL).correct


def majority_vote(candidates: Sequence[Candidate]) -> VoteOutcome:
    """Select a candidate by result-set majority vote (deterministic tiebreak).

    Groups the votable (non-errored) candidates into result-set equivalence classes
    using the comparator, picks the largest class, and returns the **earliest**
    candidate in it. A size tie between classes is broken by earliest index — so the
    selection is reproducible (§9). With every candidate errored, returns index 0
    (agreement 0) so a run is never lost.
    """
    if not candidates:
        raise ValueError("majority_vote needs at least one candidate")

    votable = [i for i, c in enumerate(candidates) if not c.errored]
    if not votable:
        return VoteOutcome(
            selected_index=0,
            agreement=0,
            n_candidates=len(candidates),
            n_votable=0,
            n_groups=0,
            tie=False,
        )

    # Equivalence classes, each a list of candidate indices, in first-seen order.
    groups: list[list[int]] = []
    for i in votable:
        for group in groups:
            if _equivalent(candidates[group[0]].result, candidates[i].result):
                group.append(i)
                break
        else:
            groups.append([i])

    # Largest class wins; a size tie is broken by the class's earliest index (the
    # groups are already in earliest-first order, so ``max`` on size is stable).
    top = max(len(g) for g in groups)
    winners = [g for g in groups if len(g) == top]
    winning = winners[0]  # earliest-first order → deterministic tiebreak
    return VoteOutcome(
        selected_index=winning[0],
        agreement=top,
        n_candidates=len(candidates),
        n_votable=len(votable),
        n_groups=len(groups),
        tie=len(winners) > 1,
    )


def candidate_from_state(state: RunState) -> Candidate:
    """Build a votable :class:`Candidate` from a completed :class:`RunState`.

    Uses the **raw verified result** (``result_rows``/``result_columns``), never the
    redacted presented result — voting is upstream of redaction, like scoring. A run
    is marked ``errored`` only when it has **no result at all** (``error`` set or
    ``result_rows is None``); a run that executed to an *empty* result stays votable
    (empty is a valid distinct result the comparator can match)."""
    return Candidate(
        result={
            "columns": state.result_columns or [],
            "rows": state.result_rows or [],
        },
        sql=state.candidate_sql,
        errored=state.error is not None or state.result_rows is None,
    )


def select_by_vote(states: Sequence[RunState]) -> tuple[RunState, VoteOutcome]:
    """Majority-vote over completed runs; return the selected run and the outcome.

    The selected run's raw result is what the harness then scores against gold — the
    scoring boundary is untouched (this only *chooses* which run to score)."""
    outcome = majority_vote([candidate_from_state(s) for s in states])
    return states[outcome.selected_index], outcome


def run_voted(
    run_one: Callable[[int], RunState], k: int
) -> tuple[RunState, VoteOutcome, tuple[RunState, ...]]:
    """Generate ``k`` candidates via ``run_one(i)``, majority-vote, return the pick.

    ``run_one(i)`` produces candidate *i*'s completed :class:`RunState` — the real
    harness wires it to run the pipeline against a
    :func:`~eval.candidate_diversity.shuffle_field_order` schema variant (and, live, a
    varied seed); a test injects recorded candidates. Returns the selected run (whose
    raw result the harness scores), the :class:`VoteOutcome`, and all candidates (so
    the caller can price the k× generation/execution cost). ``k`` candidates *is* the
    budget — this shares the multi-generation budget with self-correction, never a
    bypass (§5).
    """
    if k < 1:
        raise ValueError("run_voted needs k >= 1")
    states = tuple(run_one(i) for i in range(k))
    selected, outcome = select_by_vote(states)
    return selected, outcome, states


def agreement_distribution(outcomes: Sequence[VoteOutcome]) -> dict[str, int]:
    """Bucket vote outcomes into unanimous / majority / no-majority (plurality).

    The diagnostic that explains the gap across a batch (the deferred eval reports
    it): a strong generator skews ``unanimous`` (vote is a no-op); the value lives in
    the ``majority``/``no_majority`` questions. ``unanimous`` = one class; ``majority``
    = a strict >half winning class; ``no_majority`` = a plurality decided the pick.
    """
    buckets = {"unanimous": 0, "majority": 0, "no_majority": 0}
    for o in outcomes:
        # Denominator is the *votable* count, not n_candidates — an errored candidate
        # is excluded from the vote, so counting it would understate a real majority.
        if o.n_votable >= 1 and o.n_groups == 1:
            buckets["unanimous"] += 1
        elif o.agreement * 2 > o.n_votable:
            buckets["majority"] += 1
        else:
            buckets["no_majority"] += 1
    return buckets
