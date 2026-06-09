# Plan — Step 9: Prompt-CI/CD

**Phase:** Operations — **the senior differentiator, live**
**Headline:** A prompt change automatically tells you whether you improved or regressed.

## Goal
Externalize prompts as version-controlled templates and add a GitHub Action that runs the harness on a **frozen, seeded, stratified** slice whenever a prompt changes, posting the **pass@1/pass@k deltas**. Most portfolios never build this; it's a direct hit on JKOPay's "CI/CD for prompts and models" and SWAG's LLMOps requirements.

## Prerequisites
- A batch-capable, repeatable harness (designed that way since Step 3).
- A frozen/seeded/stratified slice (Steps 3 & 6).

## What to build
1. **Prompt templates** (`prompts/`) — Jinja-style templates with variable substitution for injected schema/few-shots (decided in the stack pass). Structured templates keep CI diffs clean (static scaffold stays put; only meaningful edits show).
2. **`.github/workflows/eval.yml`** — on change to `prompts/`, run the harness against the frozen slice and **post pass@1/pass@k deltas** (PR comment or job summary).
   - The slice is **seeded and checked into the repo** (an explicit ID list), **stratified by BIRD difficulty** so it isn't accidentally all-easy. A delta then means a real regression, not sampling variance.
   - Full BIRD is too slow/costly per push — the frozen subset is the point.
3. **Cost guard for CI** — keep the slice small enough that per-push LLM cost is acceptable; document the trade-off.

## Done when
A prompt edit triggers an **automated eval run** that reports pass@1/pass@k **deltas** against the frozen slice.

## Results log
Append an example **before/after delta** from a real prompt change (showing the CI catching a regression or confirming an improvement) with config + commit. This is a showcase artifact for the blog.

## Pitfalls
- A random-per-run subset makes deltas indistinguishable from noise — the slice **must** be frozen, seeded, and committed.
- Stratify by difficulty, or an accidentally-all-easy slice hides real regressions.
- Mind per-push API cost; that's why the slice is a fixed small subset, not full BIRD.
