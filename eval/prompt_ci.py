"""Prompt-CI: run the harness on the frozen slice and report pass@1/pass@k deltas.

The Step 9 senior differentiator, live. On every change to ``prompts/`` the CI
workflow (``.github/workflows/eval.yml``) runs the **same import-shared pipeline**
the harness measures over the frozen, seeded, stratified prompt-CI slice
(``slice_ci.json``) twice — once with the base (``main``) prompt, once with the
PR's prompt — and posts the **pass@1/pass@k deltas**. A delta means a real
regression or improvement, not sampling noise, because the slice is frozen and
stratified (plan-step-9).

This module is split so the **delta mechanism is provable offline** (defer-API-
key): :class:`PromptRunReport` (de)serialization and :func:`render_delta` are
pure functions over JSON — unit-tested without a model — while
:func:`run_ci_slice` does the live eval. The CLI has two modes::

    python -m eval.prompt_ci --report out.json          # live: run + write report
    python -m eval.prompt_ci --compare base.json out.json  # offline: render delta

The compare output is Markdown for ``$GITHUB_STEP_SUMMARY`` and the PR comment.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# --- the report: a slice run's pass@1/pass@k, pinned to its exact prompt -------


@dataclass(frozen=True)
class PromptRunReport:
    """One prompt's pass@1/pass@k over the frozen slice, pinned to its bytes.

    ``prompt_fingerprint`` is the content hash of the active template *and its
    partials* (``nl2sql.prompts.prompt_fingerprint``): two reports are only
    comparable as a prompt delta when their fingerprints differ — same
    fingerprint, same prompt, any delta is pure noise. Counts are stored (not
    rates) so the rates are exact and the Markdown can show ``n/total``.
    """

    prompt_version: str
    prompt_fingerprint: str
    model: str
    slice_name: str
    k: int
    total: int
    n_correct_1: int
    n_correct_k: int

    @property
    def pass_at_1(self) -> float:
        return self.n_correct_1 / self.total if self.total else 0.0

    @property
    def pass_at_k(self) -> float:
        return self.n_correct_k / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptRunReport:
        fields = {f for f in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in fields})

    @classmethod
    def read_json(cls, path: Path) -> PromptRunReport:
        return cls.from_dict(json.loads(path.read_text()))


# --- the delta: rendered to Markdown for the PR comment / job summary ----------


def _verdict(d1: float, dk: float) -> str:
    """Direction of the change: any drop is flagged, else any gain, else flat."""
    if d1 < 0 or dk < 0:
        return "⚠️ **Potential regression** — a pass rate dropped on the frozen slice."
    if d1 > 0 or dk > 0:
        return "✅ **Improvement** — a pass rate rose, none dropped."
    return "➡️ **No change** — pass@1 and pass@k unchanged on the frozen slice."


def _row(label: str, base: float, head: float, n_base: int, n_head: int, n: int) -> str:
    delta = head - base
    arrow = "▲" if delta > 0 else "▼" if delta < 0 else "—"
    return (
        f"| {label} | {base:.3f} ({n_base}/{n}) | {head:.3f} ({n_head}/{n}) "
        f"| {delta:+.3f} {arrow} |"
    )


def render_delta(base: PromptRunReport, head: PromptRunReport) -> str:
    """Render the base→head pass@1/pass@k delta as a Markdown block.

    Pure: the CI workflow pipes this into ``$GITHUB_STEP_SUMMARY`` and the sticky
    PR comment. Surfaces the verdict, the per-metric deltas (rate and ``n/total``),
    and the cost-guard footnote (small slice → 1 question ≈ ``1/total``, so a
    single-question flip is visible; read deltas against that granularity).
    """
    n = base.total
    same_prompt = base.prompt_fingerprint == head.prompt_fingerprint
    d1 = head.pass_at_1 - base.pass_at_1
    dk = head.pass_at_k - base.pass_at_k
    grain = 1 / n if n else 0.0

    lines = [
        "### 🧪 Prompt-CI — pass@1 / pass@k delta",
        "",
        (
            "> ⚠️ Base and PR prompts have the **same fingerprint** — no prompt "
            "change detected; any delta below is sampling noise."
            if same_prompt
            else _verdict(d1, dk)
        ),
        "",
        f"| metric | base (`{base.prompt_version}`) | PR (`{head.prompt_version}`) "
        f"| Δ |",
        "| --- | --- | --- | --- |",
        _row(
            "pass@1",
            base.pass_at_1,
            head.pass_at_1,
            base.n_correct_1,
            head.n_correct_1,
            n,
        ),
        _row(
            "pass@k",
            base.pass_at_k,
            head.pass_at_k,
            base.n_correct_k,
            head.n_correct_k,
            n,
        ),
        "",
        (
            f"_Frozen slice `{base.slice_name}` · {n} questions · "
            f"model `{base.model}` · k={base.k} · 1 question ≈ {grain:.3f}. "
            f"Base `{base.prompt_fingerprint[:14]}…` → "
            f"PR `{head.prompt_fingerprint[:14]}…`._"
        ),
    ]
    return "\n".join(lines) + "\n"


# --- the live run: same import-shared pipeline the harness measures ------------


def run_ci_slice(model: str | None = None) -> PromptRunReport:
    """Run the twin eval on the frozen prompt-CI slice → a :class:`PromptRunReport`.

    Live (needs an API key). Reuses the Step-5 twin machinery: one pass@k run over
    the slice, with pass@1 derived from its first attempts (no resampling noise).
    The report is pinned to the active prompt's version *and* fingerprint so the
    delta is attributable to exactly these prompt bytes.
    """
    from eval.datasets.bird.slice_ci import SLICE_FILE, load_ci_slice_ids
    from eval.eval_bird import build_bird_cases
    from eval.eval_bird_twin import make_factory, retry_budget
    from eval.harness import batch_session_id, derive_pass1_report, run_batch
    from eval.metrics import TwinReport
    from nl2sql import obs
    from nl2sql.pipeline.generate import DEFAULT_MODEL
    from nl2sql.prompts import PROMPT_VERSION, prompt_fingerprint

    model = model or DEFAULT_MODEL
    k = retry_budget()
    cases, evidence = build_bird_cases(slice_ids=load_ci_slice_ids())
    slice_name = json.loads(SLICE_FILE.read_text())["_meta"]["slice"]
    print(
        f"prompt-CI: twin-scoring {len(cases)} questions on `{slice_name}` "
        f"(pass@{k}); prompt {PROMPT_VERSION}…"
    )
    passk = run_batch(
        cases,
        make_factory(evidence)(k),
        session_id=batch_session_id(
            "prompt-ci", model=model, prompt_version=PROMPT_VERSION
        ),
    )
    pass1 = derive_pass1_report(passk)
    twin = TwinReport(pass1=pass1, passk=passk, model=model)
    obs.flush()
    return PromptRunReport(
        prompt_version=PROMPT_VERSION,
        prompt_fingerprint=prompt_fingerprint(),
        model=model,
        slice_name=slice_name,
        k=k,
        total=twin.pass1.total,
        n_correct_1=twin.pass1.n_correct,
        n_correct_k=twin.passk.n_correct,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--report",
        metavar="OUT.json",
        help="run the slice live and write the PromptRunReport JSON",
    )
    mode.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASE.json", "HEAD.json"),
        help="render the base→head pass@1/pass@k delta as Markdown (offline)",
    )
    parser.add_argument(
        "--out",
        metavar="DELTA.md",
        help="with --compare: also write the Markdown to this path",
    )
    args = parser.parse_args(argv)

    if args.report:
        from dotenv import load_dotenv

        load_dotenv()
        report = run_ci_slice()
        report.write_json(Path(args.report))
        print(
            f"pass@1 {report.pass_at_1:.3f} ({report.n_correct_1}/{report.total}) · "
            f"pass@{report.k} {report.pass_at_k:.3f} "
            f"({report.n_correct_k}/{report.total}) → {args.report}"
        )
        return 0

    base = PromptRunReport.read_json(Path(args.compare[0]))
    head = PromptRunReport.read_json(Path(args.compare[1]))
    markdown = render_delta(base, head)
    sys.stdout.write(markdown)
    if args.out:
        Path(args.out).write_text(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
