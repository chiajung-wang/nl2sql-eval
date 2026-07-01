"""Live twin for result-set majority voting (Step 12, #142).

Generates ``K`` candidates per question — each against a
:func:`~eval.candidate_diversity.shuffle_field_order` schema variant (candidate 0 is
the unshuffled baseline), with the model's own sampling supplying the rest of the
diversity — executes each, and selects one by :func:`eval.voting.majority_vote` (the
comparator repurposed as a selector). Reports the twin **pass@1 (attempt-1 =
candidate 0) vs pass@k (majority-selected)** for the same K, the vote-agreement
distribution, and the k× cost — the Step-5 twin pattern, a different selector over the
same multi-candidate budget.

Reuses the RAG entrypoint's per-db index/engine/case loading and the harness scorer,
so voting selects the same candidate the harness scores — the raw verified result,
upstream of redaction (§3/§5). ``K`` via the ``VOTE_K`` env (default 3). Run on a
strong (``RUN_CONFIG=accuracy``) and a weak (``MODEL=…kimi…``) generator — the value,
if any, lives on the weak one; the strong generator's candidates tend to agree (an
honest, expected null).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from eval.candidate_diversity import shuffle_field_order
from eval.datasets.bird.slice_large import load_large_slice_ids
from eval.eval_bird import build_bird_cases
from eval.eval_bird_rag import _engine, _index
from eval.harness import Case, batch_session_id, run_batch
from eval.metrics import TwinReport, twin_summary_lines
from eval.model_select import model_id
from eval.voting import agreement_distribution, run_voted
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.state import RunState
from nl2sql.prompts import PROMPT_VERSION

DIALECT = "SQLite"
RESULTS_PATH = Path(__file__).resolve().parent.parent / "RESULTS.md"


def _vote_k() -> int:
    try:
        return max(1, int(os.environ.get("VOTE_K", "3")))
    except ValueError:
        return 3


def _git_commit() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def make_vote_run_one(evidence: dict[str, str], k: int, captured: dict):
    """A ``run_one(case)`` that generates ``k`` diverse candidates and votes.

    Stashes per case the attempt-1 (candidate 0) state and the vote outcome in
    ``captured`` so the caller can build the pass@1 half of the twin and the agreement
    distribution without regenerating. Returns the majority-selected state — the one
    the harness then scores.
    """

    def run_one(case: Case) -> RunState:
        index = _index(case.db_id)

        def run_candidate(i: int) -> RunState:
            return run_pipeline(
                case.question,
                schema_index=shuffle_field_order(index, i),
                engine=_engine(case.db_id),
                db_id=case.db_id,
                dialect=DIALECT,
                evidence=evidence.get(case.id, ""),
                model=model_id(),
            )

        selected, outcome, states = run_voted(run_candidate, k)
        captured[case.id] = (states[0], outcome)
        return selected

    return run_one


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    k = _vote_k()
    ids = load_large_slice_ids()
    if limit is not None:
        ids = ids[:limit]
    cases, evidence = build_bird_cases(ids)

    captured: dict = {}
    print(f"=== majority voting, k={k} ({len(cases)} questions) · {model_id()} ===")
    passk = run_batch(
        cases,
        make_vote_run_one(evidence, k, captured),
        session_id=batch_session_id(
            "bird-vote-k", model=model_id(), prompt_version=PROMPT_VERSION
        ),
    )
    # pass@1 = candidate 0 (the unshuffled baseline), scored without regenerating.
    pass1 = run_batch(cases, lambda case: captured[case.id][0])

    twin = TwinReport(pass1, passk, model_id())
    print("\n".join(twin_summary_lines(twin)))

    dist = agreement_distribution([captured[c.id][1] for c in cases])
    print(f"\nvote-agreement distribution (k={k}): {dist}")

    row = (
        f"| {date.today().isoformat()} | 12 (#142) | pass@1→pass@k(vote) | "
        f"{twin.pass_at_1:.3f} → {twin.pass_at_k:.3f} [gap {twin.gap:+.3f}] | "
        f"{model_id()} | {load_large_slice_ids.__module__.split('.')[-1]} k={k} | "
        f"{PROMPT_VERSION} | {_git_commit()} |"
    )
    print("\nRESULTS.md row:\n" + row)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
