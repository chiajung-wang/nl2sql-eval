# Issue 4 — Env-configurable MODEL override (recorded, default pinned)

**Type:** AFK
**Phase:** Step 11 (Optimization) — *Closing the accuracy gap* · tooling for the model-swap lever

## Parent

`docs/plans/step-11/plan-step-11.md`

## What to build

The error analysis (#111/#112) pointed at the **model swap** as the lever with real headroom (`gemini-3-flash` 0.540 vs sonnet 0.420 on the dev slice). To experiment with a different generator across the runners — baseline it, diagnose it, A/B it — make the model selectable by a **`MODEL` env var**, **without** weakening the reproducibility discipline (CLAUDE.md §6).

Design mirrors `RETRY_BUDGET` (results-affecting config that's already env-driven and recorded):

- **`DEFAULT_MODEL` stays pinned in code** (`src/nl2sql/pipeline/generate.py`) as the canonical, committed default — a clean checkout reproduces the committed baseline.
- **`MODEL` is an explicit, opt-in override** layered on top; every runner **records the resolved model** in its `RESULTS.md` row, so a number always names the model that produced it. An untracked `.env` can never silently become the baseline's model.
- A shared **`model_id()`** resolver (`eval/model_select.py`) — promote the one currently local to `eval_bird_selfcorrect` — reads `MODEL`, falling back to `DEFAULT_MODEL`.
- Thread it through the runners that hardcode the model: `eval_bird`, `eval_bird_twin`, `eval_bird_rag`, `eval_bird_budget`, `eval_bird_adaptive`, `diagnose_bird`, `eval_bird_schema`, `eval_payments`.
- Document it in `.env.example`.

**Out of scope:** `eval_cross_provider` keeps its own `CROSS_PROVIDER_MODELS` list (multi-model by design). **Adopting** a new default permanently remains a *committed* `DEFAULT_MODEL` change + re-baselined `RESULTS.md` — never a `.env` edit.

## Acceptance criteria

- [ ] `MODEL` env overrides the generator model across the threaded runners; unset → the pinned `DEFAULT_MODEL` (default behavior unchanged)
- [ ] Each runner records the **resolved** model in its `RESULTS.md` row / session id
- [ ] `DEFAULT_MODEL` remains pinned in `generate.py`; `.env.example` documents `MODEL`
- [ ] Shared `model_id()` resolver; `eval_bird_selfcorrect` reuses it
- [ ] `uv run pytest` green (resolver tests: default / override / blank); lint/format clean

## Blocked by

- [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) (the diagnostic that named the model-swap lever).

---

## Tracking

**GitHub:** [#117](https://github.com/chiajung-wang/nl2sql-eval/issues/117) · label `agent-ready`, `step-11`

**PR:** _pending_

**Step 11 set:** [#111](https://github.com/chiajung-wang/nl2sql-eval/issues/111) · [#112](https://github.com/chiajung-wang/nl2sql-eval/issues/112) · [#113](https://github.com/chiajung-wang/nl2sql-eval/issues/113) · [#117](https://github.com/chiajung-wang/nl2sql-eval/issues/117)
