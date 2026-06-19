"""Prompt-CI delta mechanism — proven offline (defer-API-key).

The live slice run needs a model, but the part prompt-CI is *judged* on — pinning
a run to its exact prompt bytes and rendering a trustworthy pass@1/pass@k delta —
is pure JSON-in, Markdown-out. These tests lock that core without a model: report
round-trip, the rates derived from counts, and the verdict/delta rendering for
improvement, regression, no-change, and the same-prompt (noise) case.
"""

from __future__ import annotations

import json

from eval.prompt_ci import PromptRunReport, render_delta


def _report(
    *, n1: int, nk: int, fp: str = "sha256:base", version: str = "generate/v3"
) -> PromptRunReport:
    return PromptRunReport(
        prompt_version=version,
        prompt_fingerprint=fp,
        model="anthropic/claude-sonnet-4-6",
        slice_name="step9-prompt-ci",
        k=3,
        total=12,
        n_correct_1=n1,
        n_correct_k=nk,
    )


def test_rates_derive_from_counts():
    r = _report(n1=6, nk=9)
    assert r.pass_at_1 == 6 / 12
    assert r.pass_at_k == 9 / 12


def test_report_json_round_trips(tmp_path):
    path = tmp_path / "report.json"
    original = _report(n1=6, nk=9)
    original.write_json(path)
    loaded = PromptRunReport.read_json(path)
    assert loaded == original
    # The on-disk shape carries the fingerprint so a delta is attributable.
    assert json.loads(path.read_text())["prompt_fingerprint"] == "sha256:base"


def test_from_dict_ignores_unknown_keys():
    data = _report(n1=6, nk=9).to_dict()
    data["pass_at_1"] = 0.99  # a derived field someone may have serialized
    data["unexpected"] = "x"
    assert PromptRunReport.from_dict(data) == _report(n1=6, nk=9)


def test_render_delta_flags_regression():
    base = _report(n1=8, nk=10, fp="sha256:base")
    head = _report(n1=6, nk=9, fp="sha256:head", version="generate/v4")
    out = render_delta(base, head)
    assert "Potential regression" in out
    assert "-0.167" in out  # pass@1: 6/12 - 8/12
    assert "-0.083" in out  # pass@k: 9/12 - 10/12
    assert "`generate/v3`" in out and "`generate/v4`" in out


def test_render_delta_celebrates_improvement():
    base = _report(n1=6, nk=8, fp="sha256:base")
    head = _report(n1=8, nk=10, fp="sha256:head", version="generate/v4")
    out = render_delta(base, head)
    assert "Improvement" in out
    assert "+0.167" in out  # both metrics up by 2/12


def test_render_delta_reports_no_change():
    base = _report(n1=7, nk=9, fp="sha256:base")
    head = _report(n1=7, nk=9, fp="sha256:head", version="generate/v4")
    out = render_delta(base, head)
    assert "No change" in out
    assert "+0.000" in out


def test_render_delta_warns_when_fingerprints_match():
    # Same prompt bytes → any delta is noise; say so loudly instead of a verdict.
    base = _report(n1=7, nk=9, fp="sha256:same")
    head = _report(n1=8, nk=9, fp="sha256:same")
    out = render_delta(base, head)
    assert "same fingerprint" in out.lower()
    assert "regression" not in out.lower()
