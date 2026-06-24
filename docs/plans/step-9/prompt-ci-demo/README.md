# Prompt-CI demonstration — a regression, caught

This folder is the committed evidence for the Step 9 Definition of Done: a **real
prompt edit** triggers an automated eval run that reports **pass@1/pass@k deltas**
against the frozen slice, and the gate **catches a regression** before it merges.

## The prompt change

The demonstration prompt is [`prompts/generate/_demo_regression.jinja`](../../../../prompts/generate/_demo_regression.jinja)
— the prompt analogue of the [`fixtures/redteam_guard/`](../../../../fixtures/redteam_guard)
entries that prove the guardrails. The edit is a single, clean, `{% block rules %}`
change over the shared scaffold and **looks reasonable** — it lets the model
explain its reasoning ("First, briefly explain your approach… then provide the
SQL"). But it relaxes the load-bearing **"return ONLY the SQL"** rule: the model
now prefaces its answer with prose, the fence stripper can't unwrap it, and the
candidate is no longer valid SQL. The deterministic guard rejects it.

It is **never the active prompt** (the leading underscore marks it a non-version
artifact, like `_base.jinja`); `generate/v3` stays active. Nothing unmeasured
ships.

## The captured result

Run live with `eval.prompt_ci --report` against `anthropic/claude-sonnet-4-6` over
the frozen, seeded, stratified [`step9-prompt-ci`](../../../../eval/datasets/bird/slice_ci.py)
slice (12 questions, pass@3):

| report | prompt | pass@1 | pass@k |
| --- | --- | --- | --- |
| [`base-v3.json`](base-v3.json) | `generate/v3` (active) | 0.417 (5/12) | 0.417 (5/12) |
| [`head-regression.json`](head-regression.json) | `generate/_demo_regression` | **0.000 (0/12)** | **0.000 (0/12)** |

Rendered delta ([`delta.md`](delta.md)) — exactly what the CI workflow posts to
the job summary and the sticky PR comment:

> ⚠️ **Potential regression** — pass@1 **-0.417 ▼**, pass@k **-0.417 ▼**.

A reasonable-sounding edit took accuracy to zero, and prompt-CI caught it. (It
also surfaced a latent guard crash on untokenizable input — when prose leaked a
stray markdown fence, `sqlglot` raised `TokenError` and the run *crashed* instead
of bucketing into a terminal state. Fixed in the same PR; see
`tests/test_guard.py::test_untokenizable_sql_is_rejected_not_crashed`.)

> **A note on honesty.** On this small, stable slice, *sensible* edits don't move
> the headline: adding output-precision rules, or an `always LIMIT 1` rule, both
> measured **0.417 (5/12)** — pass@1 unchanged (the passing questions are robust
> single-row aggregates; the failures are semantically hard, echoing Step 5). The
> gate doesn't cry wolf — it greenlights neutral changes and red-flags the
> harmful one. The regression here is the catastrophic case, made
> unmistakable on purpose.

## Why these were captured by hand (and why that's the same number)

The GitHub Actions trigger ([`.github/workflows/eval.yml`](../../../../.github/workflows/eval.yml))
is **gated on `ANTHROPIC_API_KEY` + `BIRD_DEV_URL`** (defer-API-key, #58): until
those repo secrets are set, the live job posts a "skipped" note instead of
running. So the numbers here were produced by running the **exact tool the
workflow invokes** — `eval.prompt_ci` — against the live model, then rendered
with the **exact comparison the workflow runs** — `eval.prompt_ci --compare`. The
committed `delta.md` is therefore byte-for-byte what the Action would post to the
job summary and the sticky PR comment once the secrets land; nothing about the
delta changes between the hand-run and the triggered run.

## Reproduce

The proof replays the committed reports **offline** (no API key):

```bash
uv run python -m eval.prove_step9    # renders the delta, asserts a caught regression
```

To regenerate the live numbers, point the active prompt at the demonstration
template and run the CI tool (mirrors the workflow's per-ref checkout):

```bash
# temporarily set, in src/nl2sql/prompts.py:
#   GENERATE_TEMPLATE = "generate/_demo_regression.jinja"
#   PROMPT_VERSION    = "generate/_demo_regression"
uv run python -m eval.prompt_ci --report head-regression.json
git checkout src/nl2sql/prompts.py            # restore v3 as active
uv run python -m eval.prompt_ci --report base-v3.json
uv run python -m eval.prompt_ci --compare base-v3.json head-regression.json --out delta.md
```
