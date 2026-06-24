---
title: "Step 9 — A Prompt Change That Tells You If You Regressed"
subtitle: "Prompt-CI/CD: externalize prompts as clean version-controlled templates, then make every prompt edit run the harness on a frozen slice and post the pass@1/pass@k deltas — so a regression is caught before it merges, not after it ships"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 9
date: 2026-06-24
author: Chia-Jung Wang
tags: [llm, nl2sql, prompt-engineering, ci-cd, github-actions, evaluation, regression, measurement]
---

# Step 9 — A Prompt Change That Tells You If You Regressed

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness and the apparatus around it are the *product*. Step 9 is the operations
> capstone — the piece most portfolios never build. A prompt is the highest-leverage,
> easiest-to-edit, least-tested artifact in an LLM system: one word change can move
> accuracy and nobody notices until production does. Step 9 closes that gap. **A prompt
> edit now triggers an automated eval that reports the pass@1/pass@k deltas against a
> frozen slice** — so "did this prompt help or hurt?" stops being a vibe and becomes a
> number on the pull request. The Step-9 headline is the system catching exactly the
> kind of regression it exists to catch: a reasonable-looking edit that quietly took
> accuracy **0.417 → 0.000**, flagged before merge.

Every prior step measured the system on demand: you ran `eval.eval_bird_twin`, you read
the number, you reasoned about it. That's the right way to *develop* a measurement. It's
the wrong way to *operate* one — because the moment measuring is a manual step, it
becomes the step you skip under deadline, and prompts are edited under deadline more than
anything else in the stack. Step 9 makes the measurement run itself, on the one change
most likely to silently regress.

This is a direct hit on the thing real LLMOps roles ask for — "CI/CD for prompts and
models" — and it leans entirely on apparatus built in earlier steps: the batch-capable,
repeatable harness (Step 3), the frozen/seeded/stratified slice discipline (Steps 3 &
6), and the pass@1↔pass@k twin metric (Step 5). The eval was built before the feature, so
the feature is mostly wiring.

---

## #57 — Prompts as a clean, version-controlled foundation

Before you can diff a prompt change in CI, a prompt change has to *produce a clean diff*.
The prompts were already externalized Jinja templates (no prompt strings inlined in
Python — a rule since Step 1). Step 9's first issue makes them a foundation: a single
registry and a structure built for legible diffs.

The structure: the static scaffold lives once in `generate/_base.jinja`, and each version
is a thin `{% extends %}` that overrides only the blocks it changes.

```jinja
{# generate/v3.jinja — the active prompt, no overrides #}
{% extends "generate/_base.jinja" %}
```

A future `v4` that tweaks one rule is a few-line diff in one block, not a 35-line
whole-file rewrite — the scaffold stays put, so prompt-CI shows reviewers the *edit*, not
the noise around it. Extracting the scaffold was a refactor, so it had to change **zero
rendered bytes**; a golden-render test locks that the active template is byte-identical to
the prior single-file v3, with and without the correction block.

The registry (`nl2sql.prompts`) is the single source of truth: where templates live, the
active `PROMPT_VERSION` pinned into every `RESULTS.md` row, and a **content fingerprint**.
The fingerprint matters more than the version string, because a version string can lie —
someone edits a template in place and forgets to bump it. The fingerprint can't: it's a
`sha256` over the active template *and the partials it extends*, so any edit to the prompt
the model actually sees moves the hash.

```
$ python -m nl2sql.prompts --version
generate/v3
$ python -m nl2sql.prompts --fingerprint
sha256:4a12c212c6262d5d1a52542a0d11f36d1ce5ce65bc17cb035e4870e2408303cb
```

CI pins the fingerprint; a number always traces to the exact prompt bytes that produced
it.

---

## #58 — The workflow: base vs PR, on the same frozen slice

The senior differentiator, live. `.github/workflows/eval.yml` triggers on any change under
`prompts/` (and `src/nl2sql/prompts.py`, where the active version is pinned), and runs the
**same import-shared pipeline the harness measures** — never a fork — over a frozen slice
with *both* prompts:

```
PR changes prompts/**  →  run PR prompt   → head.json
                          checkout base    → base.json
                          render_delta     → job summary + sticky PR comment
```

Running base and PR in the *same job, on the same slice, model, and environment* is the
design decision that makes the delta trustworthy: there's no committed baseline that can
drift, and a delta is attributable to the prompt bytes alone. The rendered comment prints
both fingerprints; if they match, it says "no prompt change — noise" instead of inventing
a verdict.

Two pieces of discipline carried over from the rest of the project:

- **The slice is the cost guard.** Full BIRD per push is too slow and costly, so the
  prompt-CI slice is a frozen, seeded, **stratified** 12-question subset (simple 6 /
  moderate 4 / challenging 2) drawn from the small-schema dbs where the naive dump never
  overflows context. Per-push cost scales with `size × k × 2` (base + PR), not full BIRD.
  Stratified, because an accidentally-all-easy slice would hide real regressions; frozen
  and seeded, because a random-per-run subset makes a delta indistinguishable from
  sampling noise. *That's the whole point of a fixed small subset.*
- **The delta mechanism is provable offline.** The report is a small dataclass pinned to
  the prompt fingerprint; `render_delta` is a pure Markdown function. Both are unit-tested
  with synthetic reports — no model needed — so the part CI is judged on (does it report a
  trustworthy delta?) is green without spending a cent. The live run is gated on an API
  key plus a BIRD data source; without them the job posts a "skipped" note rather than
  failing the PR (the defer-API-key discipline this project runs on).

---

## #59 — Catching a real regression (and a crash we didn't know we had)

The Definition of Done is the system doing its job on a real prompt edit. Here's where the
honesty rails of the whole project earn their keep, because the first thing the live runs
told me was uncomfortable: **on this small, stable slice, sensible prompt edits don't move
the headline at all.** A genuine improvement attempt (add output-precision rules) measured
**0.417 (5/12)**. An `always LIMIT 1` rule measured **0.417 (5/12)**. The same five
questions passed each time — they're robust single-row aggregates — and the same seven
failed, because they're semantically hard, not prompt-sensitive at the margin. That's the
exact texture of the Step 5 finding ("the failures are semantic, not syntactic"), and it's
the honest backdrop: this gate does **not** cry wolf. Most edits are neutral, and it says
so.

So to demonstrate a *caught regression*, I did what this project already does for
guardrails: I fed the mechanism the thing it must catch — the prompt analogue of the
`fixtures/redteam_guard/` red-team set. The demonstrator is a single clean `{% block rules %}`
change that **looks reasonable** — let the model explain its reasoning:

```jinja
{% block rules %}- First, briefly explain your approach in one or two sentences.
- Then provide the SQL query that answers the question.
- ...
```

It relaxes the load-bearing **"return ONLY the SQL"** rule. The model now prefaces its
answer with prose, the fence stripper can't unwrap it, and the candidate is no longer valid
SQL. Over the frozen slice:

| metric | base `generate/v3` | PR `generate/_demo_regression` | Δ |
|---|---|---|---|
| pass@1 | 0.417 (5/12) | **0.000 (0/12)** | **−0.417 ▼** |
| pass@k | 0.417 (5/12) | **0.000 (0/12)** | **−0.417 ▼** |

A reasonable-sounding edit took accuracy to zero, and prompt-CI caught it before merge.
The demonstrator is never the active prompt — `generate/v3` stays active; nothing
unmeasured ships — and it's disclosed as a deliberate strawman, in the README and the
results log, precisely so the catch isn't oversold.

### The crash the demo surfaced

Then the apparatus did the thing apparatus is *for*: it found a bug I wasn't looking for.
When the model's prose leaked a stray markdown fence, the candidate was **untokenizable** —
`sqlglot` raised `TokenError` (a sibling of `ParseError`) from the guard's parse, and the
guard only caught `ParseError`. The run **crashed** instead of bucketing into a terminal
state — a direct violation of the invariant that *every run buckets into exactly one
terminal state*. A one-line fix, with a regression test:

```python
-        except ParseError:
+        except (ParseError, TokenError):   # unparseable → reject, never crash
```

Now an untokenizable candidate is a clean `parse_error` guardrail rejection. The
deterministic core stays sqlglot-AST-only — no regex, no LLM. I went looking for a prompt
regression and left having hardened the guard; that's the apparatus working on its own
author again.

---

## The number that matters: a regression, caught

| Date | Step | Metric | Number | Model | Slice | Prompt | Commit |
|---|---|---|---|---|---|---|---|
| 2026-06-24 | 9 | prompt-CI regression delta | **0.417 (5/12) → 0.000 (0/12) [Δ −0.417]** | `anthropic/claude-sonnet-4-6` | `step9-prompt-ci` | `v3 → _demo_regression` | `157fe6b` |

The numbers are real — live `anthropic/claude-sonnet-4-6` runs over the frozen slice,
committed as JSON under `docs/plans/step-9/prompt-ci-demo/`. The GitHub Action itself is
gated on secrets (defer-API-key), so these were produced by running the *exact tool the
workflow invokes* by hand; the committed `delta.md` is byte-for-byte what the Action posts
once the secrets land. Reproduce the proof offline, no key required:

```bash
uv run python -m eval.prove_step9   # renders the delta, asserts a caught regression
```

---

## What we refused to build

- **A random-per-run CI slice.** The single most tempting shortcut, and the one the plan
  forbade in capitals: a subset re-sampled each push makes every delta indistinguishable
  from sampling noise. The slice is frozen, seeded, and committed, so a non-zero delta
  means a real change.
- **An all-easy slice.** Stratifying by BIRD difficulty costs nothing and prevents the
  failure mode where the gate looks green because it only ever sees questions the model
  was always going to pass.
- **A passing-grade gate.** Step 9 *reports* the delta; it doesn't (yet) block the merge on
  a threshold. Reporting first is deliberate — a gate you can't trust the number behind is
  worse than no gate. Once the live run is wired into CI with secrets, a threshold is a
  one-line policy on a number we've already proven trustworthy.
- **Overselling the demo.** The catastrophic 0.000 is a strawman, and the writeup says so —
  alongside the neutral results that prove the gate doesn't false-alarm. A demonstration you
  have to spin is a demonstration that didn't happen.

---

## What's next

Step 9 was the operations capstone: prompts are clean and versioned, and a change to one
runs the harness and reports its delta — the measurement now operates itself on the most
edit-prone artifact in the system. The remaining work is reach, not foundation:

- **Step 10** — the demo UI and the open-source writeup: the Streamlit app built to *reveal
  the wrapper* (guardrail decision, retry count, cost, the redacted result), and the public
  case study that ties every claim back to a number, a config, and a commit.

The arc of this series has been one idea applied nine times: build the thing that can tell
you the truth before you build the thing you hope is true. Step 5 proved a feature was worth
nothing; Step 6 proved retrieval pays only where the schema overflows; Step 7 proved a
framework swap changed exactly nothing; Step 9 proves the cheapest, riskiest edit in the
whole system — a prompt — can no longer regress in silence. The measurement caught it. That
was always the product.
