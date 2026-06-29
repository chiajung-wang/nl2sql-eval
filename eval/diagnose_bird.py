"""Error analysis for the pass@1 baseline: *what* are the failures, not just how many.

pass@1 0.420 (21/50) means 29 wrong — but a count is not actionable. This runs the
frozen Step-3 slice once (single-shot, naive dump, the baseline config) and, for
every failure, emits the question, the **gold vs candidate SQL**, the comparator's
reason, and a **deterministic, sqlglot-AST-derived tag** for the likely root cause
(missing JOIN, wrong aggregate, table mismatch, missing GROUP BY/WHERE, top-N
LIMIT, projection-count, …). Tags are counted into a taxonomy so the biggest
bucket — the thing to fix first — is obvious.

The tagging is structural AST diffing only (no regex for SQL semantics, no LLM —
CLAUDE.md §4): it compares gold and candidate feature sets, it does not judge
correctness (the comparator already did that, upstream of redaction). The result
sets themselves are never emitted — only SQL, reasons, and counts — so nothing
leaks (and the BIRD slice carries no PII regardless).

    uv run python -m eval.diagnose_bird                 # run + write the report
    uv run python -m eval.diagnose_bird --out other.md  # custom output path
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import sqlglot
from dotenv import load_dotenv
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from eval.compare import BIRD_RULES, Verdict, compare
from eval.datasets.bird import loader
from eval.eval_bird import DIALECT, _engine, build_bird_cases, make_run_one
from eval.harness import Case, batch_session_id, run_batch
from eval.metrics import BatchReport
from eval.model_select import model_id
from nl2sql import obs
from nl2sql.prompts import PROMPT_VERSION

REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "docs/plans/step-3/baseline-failures.md"
)

# BIRD is SQLite; fall back to the generic parser for robustness (mirrors the
# comparator's tolerant gold parse).
_DIALECTS: tuple[str | None, ...] = ("sqlite", None)
# Wall-clock bound for re-executing an untrusted candidate during BIRD re-scoring
# (#125): generous for a legitimate query, short enough that a runaway can't hang.
_RESCORE_TIMEOUT_S = 15.0
_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)


def _parse(sql: str) -> exp.Expression | None:
    for dialect in _DIALECTS:
        try:
            tree = sqlglot.parse_one(sql, dialect=dialect)
        except (ParseError, TokenError):
            continue
        if tree is not None:
            return tree
    return None


def _features(sql: str | None) -> dict[str, Any]:
    """Structural features of a query, from its AST — the basis for diffing.

    Pure shape, no judgement: the table set, join/aggregate/group/distinct/
    where/order/limit presence, and the projection width. ``None`` SQL or an
    unparseable string yields an empty feature set (itself a signal)."""
    tree = _parse(sql) if sql else None
    if tree is None:
        return {"parsed": False}
    select = tree.find(exp.Select)
    projections = select.expressions if select is not None else []
    return {
        "parsed": True,
        "tables": frozenset(
            t.name.casefold() for t in tree.find_all(exp.Table) if t.name
        ),
        "n_joins": len(list(tree.find_all(exp.Join))),
        "aggs": frozenset(type(a).__name__.lower() for a in tree.find_all(*_AGGS)),
        "group_by": tree.find(exp.Group) is not None,
        "distinct": tree.find(exp.Distinct) is not None,
        "where": tree.find(exp.Where) is not None,
        "order_by": tree.find(exp.Order) is not None,
        "limit": tree.find(exp.Limit) is not None,
        "n_select": len(projections),
    }


def categorize(gold_sql: str, candidate_sql: str | None) -> list[str]:
    """Tag the structural differences between gold and candidate — the likely
    root cause(s) of a wrong answer. Multiple tags allowed (failures compound);
    empty means the shapes match and the error is finer (value/predicate-level)."""
    g, c = _features(gold_sql), _features(candidate_sql)
    if not c.get("parsed"):
        return ["candidate_unparseable"]
    if not g.get("parsed"):
        return ["gold_unparseable"]  # diagnostic can't compare; rare
    tags: list[str] = []
    if g["tables"] != c["tables"]:
        tags.append("table_mismatch")
    if g["n_joins"] != c["n_joins"]:
        tags.append("join_mismatch")
    if g["aggs"] != c["aggs"]:
        tags.append("aggregate_mismatch")
    if g["group_by"] != c["group_by"]:
        tags.append("group_by_mismatch")
    if g["distinct"] != c["distinct"]:
        tags.append("distinct_mismatch")
    if g["where"] != c["where"]:
        tags.append("where_mismatch")
    if g["limit"] != c["limit"]:
        tags.append("limit_mismatch")
    if g["n_select"] != c["n_select"]:
        tags.append("projection_count_mismatch")
    return tags or ["shape_matches_value_level"]


def _failure_records(
    report: BatchReport, by_id: dict[str, Case]
) -> list[dict[str, Any]]:
    """Join each failed case back to its gold/question/evidence + AST tags."""
    records = []
    for r in report.results:
        if r.correct:
            continue
        case = by_id[r.case_id]
        records.append(
            {
                "id": r.case_id,
                "db_id": r.db_id,
                "difficulty": r.difficulty,
                "terminal_state": r.terminal_state.value,
                "question": case.question,
                "gold_sql": case.gold_sql,
                "candidate_sql": r.candidate_sql,
                "comparator_reason": r.note,
                "tags": categorize(case.gold_sql, r.candidate_sql),
            }
        )
    return records


def rescore_under_bird(records: list[dict[str, Any]]) -> None:
    """Annotate each failure with whether it passes **BIRD set semantics**.

    Our default comparator is deliberately stricter (multiset, order-aware); BIRD's
    official evaluator de-dupes (``set(...)``). Re-executing gold + candidate and
    re-comparing under :data:`BIRD_RULES` separates **scorer-strictness
    false-negatives** (a query BIRD would accept) from **genuine model errors** —
    the only ones worth fixing. SQLite-only, no model. Mutates ``records``."""
    for r in records:
        r["bird_correct"] = False
        if not r["candidate_sql"]:
            continue
        try:
            engine = _engine(r["db_id"])
            gold = loader.run_query(engine, r["gold_sql"])
            # The candidate is untrusted model output: a truncated/garbled query
            # can parse yet execute as a runaway (e.g. an unbounded cross-join),
            # which would hang the whole diagnostic. Bound it (#125); a timeout
            # is just another genuine failure.
            cand = loader.run_query(
                engine, r["candidate_sql"], timeout=_RESCORE_TIMEOUT_S
            )
            r["bird_correct"] = (
                compare(gold, cand, r["gold_sql"], rules=BIRD_RULES).verdict
                is Verdict.CORRECT
            )
        except Exception:  # noqa: BLE001 — an unexecutable candidate is a genuine fail
            pass


def _render_report(
    report: BatchReport, records: list[dict[str, Any]], model: str
) -> str:
    """Markdown: headline, taxonomy counts, by-difficulty/db cuts, per-failure."""
    scorer_artifacts = [r for r in records if r.get("bird_correct")]
    genuine = [r for r in records if not r.get("bird_correct")]
    bird_correct = report.n_correct + len(scorer_artifacts)
    # Taxonomy over the GENUINE errors only — scorer artifacts aren't model bugs.
    tax = Counter(t for rec in genuine for t in rec["tags"])
    by_diff = report.pass_at_1_by("difficulty")
    by_db = report.pass_at_1_by("db_id")
    terminal = report.terminal_counts()

    lines = [
        "# BIRD baseline — failure analysis",
        "",
        f"**pass@1 {report.pass_at_1:.3f} ({report.n_correct}/{report.total})** "
        f"(strict multiset default) · model `{model}` · prompt "
        f"`{PROMPT_VERSION}` · single-shot, naive schema dump.",
        "",
        "## Scorer artifact vs genuine model error",
        "",
        "Our comparator defaults to **strict multiset** semantics; BIRD's official "
        "evaluator de-dupes (`set(...)`). Re-scoring the failures under `BIRD_RULES` "
        "separates the two:",
        "",
        f"- **pass@1 under BIRD set-semantics: {bird_correct / report.total:.3f} "
        f"({bird_correct}/{report.total})** — `+{len(scorer_artifacts)}` vs the "
        f"strict default.",
        f"- **{len(scorer_artifacts)}** failures are **scorer-strictness "
        f"false-negatives** (BIRD would accept them); **{len(genuine)}** are "
        f"**genuine model errors** — the real target.",
        "",
        "## Genuine-error taxonomy (the biggest bucket is what to fix first)",
        "",
        "Deterministic sqlglot-AST diffs of gold vs candidate, over the genuine "
        "errors only (a query may carry several tags).",
        "",
        "| root-cause tag | genuine failures |",
        "| --- | --- |",
    ]
    lines += [f"| {tag} | {n} |" for tag, n in tax.most_common()]
    lines += [
        "",
        "## pass@1 by difficulty",
        "",
        "| difficulty | pass@1 |",
        "| --- | --- |",
    ]
    lines += [
        f"| {k} | {v:.3f} |"
        for k, v in sorted(by_diff.items(), key=lambda kv: str(kv[0]))
    ]
    lines += ["", "## pass@1 by db", "", "| db | pass@1 |", "| --- | --- |"]
    lines += [f"| {k} | {v:.3f} |" for k, v in sorted(by_db.items())]
    lines += [
        "",
        "## terminal states",
        "",
        "| state | count |",
        "| --- | --- |",
    ]
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


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else REPORT_PATH
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    model = model_id()
    # SLICE=holdout diagnoses the held-out slice (Step-11 protocol: validate a
    # dev lift there); default is the dev (Step-3) slice.
    if os.environ.get("SLICE") == "holdout":
        from eval.datasets.bird.slice_step11_holdout import load_holdout_slice_ids

        slice_ids: list[int] | None = load_holdout_slice_ids()
        slice_label = "step11-holdout"
    else:
        slice_ids, slice_label = None, "step3-dev"
    cases, evidence = build_bird_cases(slice_ids=slice_ids)
    by_id = {c.id: c for c in cases}
    print(
        f"diagnosing {len(cases)} BIRD questions ({DIALECT}, naive dump, single-shot) "
        f"on `{model}` · slice `{slice_label}`…"
    )
    report = run_batch(
        cases,
        make_run_one(evidence, model),
        session_id=batch_session_id(
            "bird-diagnose", model=model, prompt_version=PROMPT_VERSION
        ),
    )
    records = _failure_records(report, by_id)
    rescore_under_bird(records)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_report(report, records, model))
    out.with_suffix(".json").write_text(json.dumps(records, indent=2) + "\n")

    genuine = [r for r in records if not r.get("bird_correct")]
    artifacts = len(records) - len(genuine)
    tax = Counter(t for rec in genuine for t in rec["tags"])
    print(
        f"\npass@1 {report.pass_at_1:.3f} ({report.n_correct}/{report.total}) strict / "
        f"{(report.n_correct + artifacts) / report.total:.3f} BIRD set-semantics"
    )
    print(
        f"{len(records)} failures: {artifacts} scorer artifacts, {len(genuine)} genuine"
    )
    print("genuine-error taxonomy:", dict(tax.most_common()))
    print(f"wrote {out} (+ .json)")
    obs.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
