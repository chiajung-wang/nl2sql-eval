"""Step 9 proof: prompt-CI catches a real prompt-change regression.

The Step-9 Definition of Done is a prompt edit that triggers an automated eval
run reporting pass@1/pass@k deltas against the frozen slice — a regression caught
or an improvement confirmed. This script is the committed, **offline** proof of
that: it replays the two captured live reports under
``docs/plans/step-9/prompt-ci-demo/`` (base ``generate/v3`` vs the deliberately-
harmful ``generate/_demo_regression`` demonstration prompt), renders the delta
exactly as the CI workflow does, and asserts the gate caught the regression.

The numbers are real — produced by ``eval.prompt_ci --report`` against the live
model over the frozen ``step9-prompt-ci`` slice — and committed as JSON so the
proof needs no API key (defer-API-key). The harmful edit relaxes the load-bearing
"return ONLY the SQL" rule to let the model explain itself; its prose breaks SQL
extraction, so pass@1 collapses **0.417 → 0.000 (-0.417)**. Reproduce the live
numbers by pointing the active prompt at ``generate/_demo_regression`` and
re-running ``eval.prompt_ci`` (see ``docs/plans/step-9/prompt-ci-demo/README.md``).

    uv run python -m eval.prove_step9

Prints the rendered delta and exits non-zero unless the gate's verdict is a
caught regression — so this proof is itself CI-checkable.
"""

from __future__ import annotations

from pathlib import Path

from eval.prompt_ci import PromptRunReport, render_delta

DEMO_DIR = Path(__file__).resolve().parents[1] / "docs/plans/step-9/prompt-ci-demo"
BASE_REPORT = DEMO_DIR / "base-v3.json"
HEAD_REPORT = DEMO_DIR / "head-regression.json"


def prove(base_path: Path = BASE_REPORT, head_path: Path = HEAD_REPORT) -> int:
    """Replay the captured reports, render the delta, assert a regression caught."""
    base = PromptRunReport.read_json(base_path)
    head = PromptRunReport.read_json(head_path)
    print(render_delta(base, head))

    if base.prompt_fingerprint == head.prompt_fingerprint:
        print("FAIL: base and head share a fingerprint — no prompt change to score.")
        return 1
    d1 = head.pass_at_1 - base.pass_at_1
    dk = head.pass_at_k - base.pass_at_k
    if d1 < 0 or dk < 0:
        print(
            f"PASS: prompt-CI caught the regression — pass@1 {d1:+.3f}, "
            f"pass@k {dk:+.3f} on the frozen `{base.slice_name}` slice."
        )
        return 0
    print("FAIL: expected a caught regression but the deltas did not drop.")
    return 1


def main() -> int:
    return prove()


if __name__ == "__main__":
    raise SystemExit(main())
