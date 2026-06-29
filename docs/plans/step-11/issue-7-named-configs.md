# Issue 7 — Two named configs: bank the validated model swap

**Type:** AFK
**Phase:** Step 11 follow-up (Optimization) — *ship the win, don't leave it in prose*

## Parent

`docs/plans/step-11/plan-step-11.md`

## Motivation (a measured win that only lives in the README)

The single largest lift Step 11 found is the **model swap**, and it is fully
validated: `gemini-3.5-flash` (with `MAX_TOKENS=4096`) scores **pass@1 0.520
strict / 0.580 BIRD set-semantics** on the dev slice — the top model, **+0.10
BIRD over the sonnet baseline** (RESULTS.md → Step 11 #124). Unlike a tuned
prompt it carries **no slice-overfitting risk** (the model was never tuned on
these questions), so the direction is trustworthy without a held-out shot.

But the win is currently only **recommended in README prose and `.env.example`**.
The pinned `DEFAULT_MODEL` stays `anthropic/claude-sonnet-4-6` for a real reason:
gemini routes through OpenRouter, which forfeits clean list-priced cost
accounting (`cost_usd` doesn't price OpenRouter models — #52). That tension —
*best accuracy vs. clean cost accounting* — shouldn't be resolved by leaving the
better number undiscoverable. **Ship both as named configs** so a user picks the
axis they care about with one switch, instead of hand-assembling `MODEL` +
`MAX_TOKENS` from a README paragraph.

## What to build

Two **named, version-controlled run configs** the harness/demo can select by
name (not loose env vars a reader has to reconstruct):

- **`accuracy`** — `openrouter/google/gemini-3.5-flash`, `MAX_TOKENS=4096`,
  active prompt `generate/v3`. The top-of-slice config (0.520 / 0.580).
- **`list-priced`** (default) — `anthropic/claude-sonnet-4-6`, the direct,
  list-priced model that keeps `cost_usd` accounting honest. Stays the pinned
  default for the cost-accounting reason in #117/#117-follow-up.

Requirements:
- A single source of truth for each config (model + token budget + prompt
  version + dialect) that both `eval/harness.py` and `apps/demo/` consume — **no
  config duplication across the import-shared pipeline** (CLAUDE.md §3).
- Selecting a config by name reproduces the exact RESULTS.md row for that config
  (so `accuracy` reproduces 0.520/0.580; `list-priced` reproduces 0.420/0.460).
- `DEFAULT_MODEL`/default behavior is **unchanged** when no config is named — a
  bare run is still the list-priced default. This issue *adds a selector*, it
  doesn't repin the default.
- README + `.env.example` updated to document the named configs in one place,
  replacing the assemble-it-yourself prose.

## Evaluation protocol

- No new accuracy claim — this issue **banks existing measured numbers**, it
  doesn't tune. The check is *reproduction*: running each named config
  reproduces its committed RESULTS.md pass@1 (strict and BIRD set-semantics).
- If a config is run live to confirm reproduction, append a row with full config
  + commit (CLAUDE.md §6); otherwise cite the existing #124 / baseline rows.

## Acceptance criteria

- [ ] Two named configs (`accuracy`, `list-priced`) defined in one place,
      consumed by both the harness and the demo — no duplicated pipeline/model
      config (CLAUDE.md §3 import-sharing intact)
- [ ] `accuracy` config bundles `gemini-3.5-flash` + `MAX_TOKENS=4096`;
      `list-priced` is the unchanged sonnet default
- [ ] Default (no config named) behavior is byte-identical to today
- [ ] README + `.env.example` document the named configs; prose-only assembly
      instructions removed
- [ ] `uv run pytest` green; lint/format clean
- [ ] **(Deferred live run, gated on key/spend — [[defer-api-key-verification]])**
      a reproduction run per config confirming its RESULTS.md numbers, recorded
      with full config + commit

## Out of scope

- Repinning the global `DEFAULT_MODEL` to gemini (the OpenRouter cost-accounting
  objection from #117 stands).
- Adding new models or a new accuracy lever (that is issue-9/issue-10).
- Pricing OpenRouter models in `cost_usd` (separate concern, #52).

## Blocked by

- None. The numbers it banks already landed (#124). Independent of the
  table-selection work; can ship first as the lowest-risk Step 11 follow-up.

---

## Tracking

**GitHub:** [#132](https://github.com/chiajung-wang/nl2sql-eval/issues/132) · label `agent-ready`, `step-11`

**PR:** _pending_

**Step 11 follow-up set:** #121 · #122 · **#132 (this)** · #133 (wider slice) ·
#134 (table-selection root cause) · #135 (explicit table pre-selection)
