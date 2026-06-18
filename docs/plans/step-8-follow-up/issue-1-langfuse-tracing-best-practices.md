# Issue 1 — Langfuse tracing best-practices pass (skill audit → trace I/O, tags, region host, smoke verifier)

**Type:** AFK
**Phase:** Step 8 follow-up — *Operations (observability), pre-blog*

## Parent

`docs/plans/step-8-follow-up/plan-step-8-follow-up.md`

## What to build

Install the official **Langfuse skill** (`langfuse/skills`), run its
`references/instrumentation.md` baseline audit over the Step-8 wiring, and close
the gaps it surfaces. The audit scored the existing instrumentation well
(model/tokens/cost on the `generate` generation, span hierarchy, observation
types, PII masking, `flush()` already covered by the SDK's `atexit`). It surfaced
**one unmet baseline** (trace input/output) and — once live keys were added — one
**silent blocker** (region host). Deliver:

1. **Trace input/output on the root `pipeline` span (the baseline fix).** Record
   the NL **question** as the trace input (the user's own message — the skill's
   recommended input, distinct from PII pulled out of the database) and the
   **presented (redacted) result shape** as the output: row/column counts, the
   generated SQL, attempts, guard flag. **Counts and shapes only — never raw
   rows** (CLAUDE.md §5.3). Add a `trace_input` parameter to `obs.stage_span`;
   in v4 the root observation's input/output becomes the trace's.

2. **Trace-level attributes via v4 `propagate_attributes`.** A new
   `obs.trace_attributes(...)` context manager that names the trace (`nl2sql`),
   tags it `db:<id>` / `model:<id>` for UI filtering, and accepts an optional
   `session_id` (for future batch grouping). **Offline-safe**: a no-op with no
   client; any Langfuse failure degrades to a plain pass-through.

3. **Region-robust host resolution (the blocker).** The Python SDK reads
   `LANGFUSE_HOST`; the CLI reads `LANGFUSE_BASE_URL`. With only the latter set
   (e.g. JP `https://jp.cloud.langfuse.com`) `Langfuse()` defaults to EU and the
   keys silently fail to auth. `obs._build_client()` must resolve the host from
   `LANGFUSE_HOST` **or** `LANGFUSE_BASE_URL` and pass it explicitly.

4. **Smoke verifier.** `eval/langfuse_smoke.py`: `auth_check` → emit one trace
   through the **real** `obs` seam (a `pipeline` root with a nested `generation`,
   safe shapes only) → flush → print the trace URL. Offline → "disabled", sends
   nothing, exits non-zero.

5. **Determinism + docs.** Explicit `obs.flush()` at the end of the
   `eval.eval_bird` / `eval.eval_payments` batch mains (belt-and-suspenders with
   the SDK `atexit`). README "reproduce the trace" block + region host note;
   `.env.example` region guidance.

## Invariants to honor (CLAUDE.md)

- **Raw PII never reaches a span** (§5.3) — only the NL question and result
  *shapes/counts* are attached; redaction discipline and the `prove_step8` no-PII
  gate stay intact.
- **Observability is a seam, never a dependency** — every new path is offline-safe
  and best-effort; a Langfuse hiccup must not break a run.
- **Import-sharing** (§3) — the demo and harness hit the same `run_pipeline` /
  `obs` seam; no forked instrumentation.
- **Documentation-first** — use the current Langfuse **v4** API
  (`propagate_attributes`, root-observation I/O), not the deprecated
  `update_current_trace`.

## Acceptance criteria

- [ ] Root `pipeline` trace shows **question in / result-shape out**, tagged
      `db:` / `model:`; only counts/SQL/flags as output, never rows
- [ ] `obs.trace_attributes` + `trace_input` are offline-safe (no-op without a
      client; failures degrade to pass-through) — unit-tested with a fake recorder
- [ ] `obs._build_client()` honors `LANGFUSE_HOST` **or** `LANGFUSE_BASE_URL`
- [ ] `eval/langfuse_smoke.py` runs `auth_check`, emits one trace via the real
      seam, flushes, prints the URL; offline it reports disabled and sends nothing
- [ ] Explicit `obs.flush()` in the batch entrypoints; README + `.env.example`
      updated; Langfuse skill installed
- [ ] `prove_step8` no-PII gate still passes; `uv run pytest` green; `ruff check`
      + `ruff format --check` clean

## Notes

- Live-verified once: the smoke verifier authenticated against a **JP** region
  project and printed a trace URL — proving the host fix. Per the defer-API-key
  discipline, the offline tests (fake recorder) remain the source of truth in CI.
- **Out of scope (next follow-up):** wiring `session_id` through the harness so a
  whole eval batch groups into one Session — the seam supports it, but the harness
  change is separate. LiteLLM's native Langfuse callback is also deferred (the
  manual generation already captures model/tokens/cost and keeps prompts off the
  trace by design).

## Tracking

**GitHub:** [#94](https://github.com/chiajung-wang/nl2sql-eval/issues/94) · label `agent-ready`, `step-8`

**PR:** _pending_
