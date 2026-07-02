"""pass@1 on the frozen Mini-Dev slice, via schema-RAG.

BIRD Mini-Dev (see ``eval/datasets/bird/slice_minidev.py``) is a 500-question,
upstream-curated, difficulty-stratified subset spanning both small- and
large-schema dbs from the same dev pool. Unlike Step 3's naive-dump baseline, this
runs the **schema-RAG** arm (``retrieve`` selects tables, same as Step 6+) since
Mini-Dev includes large-schema dbs a full dump would overflow — this is meant as a
larger, community-vetted number for the *current* pipeline, not a retrieval-lift
measurement (that's Step 6's job on the small `slice_step6` slice).

Reuses ``eval_bird_rag.make_rag_run_one``, so every A/B axis it already wires
(``LINK_STRATEGY``, ``SOUNDNESS``, ``RETRY_BUDGET``, ``LITERAL_STEER``,
``METADATA_SOURCE``) works unchanged here — this is the same schema-RAG path, over
a different (larger, corrected-gold) question pool.

    uv run python -m eval.eval_bird_minidev             # run + append RESULTS.md
    uv run python -m eval.eval_bird_minidev --dry-run   # run + print, no write
    uv run python -m eval.eval_bird_minidev --limit 10  # tiny subset (wiring check)
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from eval.datasets.bird import loader
from eval.datasets.bird.slice_minidev import SLICE_FILE, load_minidev_slice_ids
from eval.diagnose_bird import _failure_records, rescore_under_bird
from eval.eval_bird import RESULTS_PATH, _git_commit, append_results, build_bird_cases
from eval.eval_bird_rag import make_rag_run_one
from eval.harness import Case, batch_session_id, run_batch
from eval.metrics import BatchReport, summary_lines
from eval.model_select import model_id
from nl2sql import obs
from nl2sql.prompts import PROMPT_VERSION

FAILURE_REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "docs/plans/step-12/minidev-failures.md"
)


def slice_minidev_id() -> str:
    return json.loads(SLICE_FILE.read_text())["_meta"]["slice"]


def results_row(
    report: BatchReport, *, model: str, prompt_version: str, commit: str
) -> str:
    """Format the RESULTS.md log row (CLAUDE.md §6 — full config). No numbered
    Step owns this slice, so the Step column records the slice name instead of
    fabricating a step number."""
    number = f"{report.pass_at_1:.3f} ({report.n_correct}/{report.total})"
    return (
        f"| {date.today().isoformat()} | minidev | pass@1 (schema-RAG) | {number} | "
        f"{model} | {slice_minidev_id()} | {prompt_version} | {commit} |"
    )


def _triage(
    report: BatchReport, cases: list[Case]
) -> tuple[list[dict[str, Any]], Counter]:
    """Tag every non-``success`` case with its likely root cause.

    Reuses ``diagnose_bird``'s deterministic sqlglot-AST diffing (no regex/LLM for
    SQL semantics, CLAUDE.md §4) and its BIRD-set-semantics rescore — the same
    taxonomy the Step-3 baseline report uses, so a tag means the same thing here as
    there. Offline once ``report`` exists: no extra model calls."""
    by_id = {c.id: c for c in cases}
    records = _failure_records(report, by_id)
    rescore_under_bird(records)
    genuine = [r for r in records if not r.get("bird_correct")]
    tax = Counter(t for rec in genuine for t in rec["tags"])
    return records, tax


def _render_failure_report(
    report: BatchReport, records: list[dict[str, Any]], *, model: str
) -> str:
    """Markdown: taxonomy counts, then each failure's gold vs candidate SQL."""
    scorer_artifacts = [r for r in records if r.get("bird_correct")]
    genuine = [r for r in records if not r.get("bird_correct")]
    bird_correct = report.n_correct + len(scorer_artifacts)
    tax = Counter(t for rec in genuine for t in rec["tags"])
    terminal = report.terminal_counts()

    lines = [
        "# Mini-Dev — failure analysis",
        "",
        f"**pass@1 {report.pass_at_1:.3f} ({report.n_correct}/{report.total})** "
        f"(strict multiset default) · model `{model}` · prompt `{PROMPT_VERSION}` · "
        f"schema-RAG, single-shot, slice `{slice_minidev_id()}`.",
        "",
        f"pass@1 under BIRD set-semantics: **{bird_correct / report.total:.3f} "
        f"({bird_correct}/{report.total})** — `+{len(scorer_artifacts)}` scorer-"
        f"strictness false-negatives vs `{len(genuine)}` genuine model errors.",
        "",
        "## Genuine-error taxonomy",
        "",
        "Deterministic sqlglot-AST diffs of gold vs candidate (a failure may carry "
        "several tags).",
        "",
        "| root-cause tag | genuine failures |",
        "| --- | --- |",
    ]
    lines += [f"| {tag} | {n} |" for tag, n in tax.most_common()]
    lines += ["", "## terminal states", "", "| state | count |", "| --- | --- |"]
    lines += [f"| {s.value} | {c} |" for s, c in terminal.items() if c]
    lines += ["", "## Failures (gold vs candidate)", ""]
    for rec in records:
        flag = " · **BIRD-ok (scorer artifact)**" if rec.get("bird_correct") else ""
        lines += [
            f"### `{rec['id']}` · {rec['db_id']} · {rec['difficulty']} · "
            f"_{rec['terminal_state']}_ · tags: {', '.join(rec['tags'])}{flag}",
            "",
            f"**Q:** {rec['question']}",
            "",
            "```sql",
            "-- gold",
            rec["gold_sql"],
            "-- candidate",
            (rec["candidate_sql"] or "(no SQL)"),
            "```",
            f"comparator: {rec['comparator_reason'] or '—'}",
            "",
        ]
    return "\n".join(lines) + "\n"


def _triage_note(
    report: BatchReport, records: list[dict[str, Any]], tax: Counter
) -> str:
    """The prose paragraph appended to RESULTS.md alongside the pass@1 row."""
    scorer_artifacts = len(records) - sum(
        1 for r in records if not r.get("bird_correct")
    )
    genuine = len(records) - scorer_artifacts
    top = ", ".join(f"**{tag}** ({n})" for tag, n in tax.most_common(5))
    return (
        f"\n**Mini-Dev — failure triage.** Of the {len(records)} non-success cases "
        f"on `{slice_minidev_id()}`, **{scorer_artifacts}** are scorer-strictness "
        f"false-negatives (BIRD set-semantics would accept them) and **{genuine}** "
        f"are genuine model errors. Deterministic sqlglot-AST tagging (reusing "
        f"`diagnose_bird`'s taxonomy, CLAUDE.md §4) of the genuine errors, biggest "
        f"first: {top}. Full per-question gold-vs-candidate detail: "
        f"`docs/plans/step-12/{FAILURE_REPORT_PATH.name}`.\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    write = "--dry-run" not in args
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ids = load_minidev_slice_ids()
    if limit is not None:
        ids = ids[:limit]
    cases, evidence = build_bird_cases(ids, questions=loader.load_minidev_questions())

    model = model_id()
    print(f"scoring {len(cases)} Mini-Dev questions (schema-RAG) on `{model}`…")
    report = run_batch(
        cases,
        make_rag_run_one(evidence),
        session_id=batch_session_id(
            "bird-minidev-rag", model=model, prompt_version=PROMPT_VERSION
        ),
    )
    print("\n" + "\n".join(summary_lines(report)))

    records, tax = _triage(report, cases)
    print(f"\n{len(records)} non-success cases — genuine-error taxonomy:")
    print(dict(tax.most_common()))

    row = results_row(
        report, model=model, prompt_version=PROMPT_VERSION, commit=_git_commit()
    )
    print("\nRESULTS.md row:\n" + row)
    if write and limit is None:
        append_results(row)
        FAILURE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        FAILURE_REPORT_PATH.write_text(
            _render_failure_report(report, records, model=model)
        )
        RESULTS_PATH.write_text(
            RESULTS_PATH.read_text().rstrip()
            + "\n"
            + _triage_note(report, records, tax)
        )
        print(f"\nappended to {RESULTS_PATH.name}; wrote {FAILURE_REPORT_PATH}")
    elif limit is not None:
        print("\n(--limit run: not writing RESULTS.md)")
    # Short-lived job: export buffered Langfuse spans before exit. A no-op offline
    # and redundant with the SDK's atexit flush, but makes export deterministic.
    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
