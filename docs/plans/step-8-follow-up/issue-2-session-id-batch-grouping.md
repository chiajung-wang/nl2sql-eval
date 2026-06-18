# Issue 2 — Group each eval batch under one Langfuse `session_id`

**Type:** AFK
**Phase:** Step 8 follow-up — *Operations (observability), pre-blog*

## Parent

`docs/plans/step-8-follow-up/plan-step-8-follow-up.md`

## Context

Issue #94 landed the seam this issue consumes: `obs.trace_attributes(session_id=…)`
already accepts a session id, but nothing threads one, so every question's trace is
standalone. Grouping a whole eval batch under one Langfuse **Session** makes eval
runs comparable in the Sessions view (one batch = one session, its per-question
traces nested) — the most useful "operate the system" upgrade for an eval product,
and the explicit *next-follow-up* deferred by #94.

## What to build

Wire the **harness** (not `run_pipeline`) so one `run_batch` / `run_twin`
invocation groups into one Session. No `run_pipeline` signature change is needed:
v4 `propagate_attributes` propagates to all child observations in scope, so
wrapping the batch loop is sufficient.

- In `eval/harness.py`, wrap the per-case loop in
  `obs.trace_attributes(session_id=<run_id>)` so every `run_one(case)` trace
  inherits the session. Apply to both `run_batch` and `run_twin`.
- Generate a stable, descriptive **run id** —
  e.g. `f"{slice_or_db}:{model}:{prompt_version}:{utc_date}"` (or a short
  timestamp). Readable in the UI, stable enough to find a run, not so unique that
  re-runs can't be compared. Decide and document the format.
- Thread the run id from the entrypoints (`eval.eval_bird*`, `eval.eval_payments`,
  `eval.eval_cross_provider`) so each names its session meaningfully (cross-provider
  puts the model in the id). Optionally tag the session with `prompt_version`.

## Invariants (CLAUDE.md)

- **Offline-safe** — `trace_attributes` already no-ops without a client; add no
  dependency and no behavior change to offline/CI runs.
- **No PII** — a `session_id` is a run identifier (slice / model / date), never user
  or result data (§5.3).
- **Don't break the injected-runner test seam** — `run_batch` takes an injected
  `run_one`; the offline harness tests must stay green.
- **Import-sharing** — the demo and harness still share `run_pipeline`; only the
  harness gains the session wrapper.

## Acceptance criteria

- [ ] `run_batch` and `run_twin` wrap their loop in
      `obs.trace_attributes(session_id=…)`; per-question traces inherit the session
- [ ] A documented, stable run-id format; entrypoints pass a meaningful id
      (cross-provider includes the model)
- [ ] Offline-safe, no behavior change without keys; harness tests green
- [ ] Unit test: the wrapper is entered with the expected `session_id` (fake
      recorder / monkeypatched `propagate_attributes`)
- [ ] `uv run pytest` green; lint/format clean; README note on the Sessions view
- [ ] Live (optional, defer-API-key): one batch produces one Session grouping its
      question traces

## Out of scope

LiteLLM's native Langfuse callback (still deferred — the manual generation captures
model/tokens/cost and keeps prompts off the trace by design).

## Tracking

**GitHub:** [#96](https://github.com/chiajung-wang/nl2sql-eval/issues/96) · label `agent-ready`, `step-8`

**PR:** _pending_
