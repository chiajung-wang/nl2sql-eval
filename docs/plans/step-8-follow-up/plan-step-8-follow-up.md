# Plan — Step 8 follow-up: a Langfuse tracing best-practices pass

**Phase:** Step 8 (Operations) — *follow-up, pre-blog*

## Why this exists

Step 8 wired the `obs/` seams to Langfuse and proved a failing question is
**diagnosable from its trace** with no raw PII (issues #54–#56). That landed the
*mechanism*. This follow-up runs the **Langfuse skill's own instrumentation audit**
over the wired code, closes the one unmet baseline it surfaces, and — once real
keys were added — fixes the one thing that silently blocks export.

The trigger: we installed the official **Langfuse skill** (`langfuse/skills`) and
ran its `references/instrumentation.md` baseline checklist against the Step-8
wiring. The instrumentation scored well — model/tokens/cost on the `generate`
generation, correct span hierarchy, observation types, PII masking, and (it turns
out) `flush()` already covered by the SDK's own `atexit`. **One baseline was
unmet:** the root `pipeline` span captured neither the question nor the result, so
a trace was not readable at its top level. Then, wiring live keys exposed a
**region/host blocker** the skill explicitly warns about.

## The findings (from the skill audit)

1. **Trace input/output missing (the one unmet baseline).** The root `pipeline`
   span recorded only `db_id` / `max_attempts` metadata — no input, no output. A
   reviewer opening the trace saw a nameless root and had to drill into child
   spans to learn what was asked and what came back.
2. **No trace-level identity/filtering.** No `trace_name`, tags, or `session_id`,
   so traces weren't filterable by db/model in the UI and an eval batch couldn't
   be grouped into one Session.
3. **Region/host blocker.** The Python SDK reads `LANGFUSE_HOST`; the
   `langfuse-cli` reads `LANGFUSE_BASE_URL`. With only `LANGFUSE_BASE_URL` set
   (e.g. `https://jp.cloud.langfuse.com`), `Langfuse()` silently defaults to **EU
   cloud** and the region keys fail to authenticate — **no traces, no error**.
4. **No end-to-end confirmation path.** Nothing let you confirm "traces actually
   land" from keys alone, short of running a full eval batch.

## The deliverables

1. **Trace I/O on the root span (the baseline fix).** Record the NL **question**
   as the trace input and the **presented (redacted) result shape** — row/column
   counts, the generated SQL, attempts, guard flag — as the trace output. Counts
   and shapes only, **never raw rows** (CLAUDE.md §5.3). The question is the
   user's own message (the skill's recommended input), distinct from PII pulled
   from the database into results.
2. **Trace-level attributes via v4 `propagate_attributes`.** A `trace_attributes`
   context manager on the `obs` seam — offline-safe — that names the trace and
   tags it `db:<id>` / `model:<id>`, and carries an optional `session_id` so a
   whole eval batch can group into one Session.
3. **Region-robust host resolution.** `obs._build_client()` resolves the host
   from `LANGFUSE_HOST` **or** `LANGFUSE_BASE_URL` and passes it explicitly, so a
   non-EU region works without renaming env vars.
4. **A smoke verifier.** `eval/langfuse_smoke.py`: `auth_check` → emit one trace
   through the *real* `obs` seam → flush → print the trace URL. Offline it reports
   "disabled" and sends nothing.
5. **Determinism + docs.** Explicit `obs.flush()` at the end of the batch
   entrypoints (belt-and-suspenders with the SDK `atexit`); README "reproduce the
   trace" block + region host note; `.env.example` region guidance.

## Definition of done (follow-up)

- Root `pipeline` trace shows **question in / result-shape out**, tagged
  `db:` / `model:` — verified offline (fake recorder) and live.
- `trace_attributes` and the `trace_input` seam are **offline-safe**: a no-op with
  no client, and any Langfuse failure degrades to a plain pass-through.
- Host resolves from `LANGFUSE_HOST` or `LANGFUSE_BASE_URL`; a non-EU region
  authenticates (confirmed live via the smoke verifier).
- `eval/langfuse_smoke.py` exists and is offline-safe; README + `.env.example`
  updated; the Langfuse skill is installed.
- No raw PII can reach a span (the existing Step-8 guarantee preserved); the
  `prove_step8` no-PII gate still passes.
- `uv run pytest` green; `ruff check` + `ruff format --check` clean; module
  boundaries + import-sharing intact (demo and harness share the same seam).
- Follow-up blog written under `docs/blogs/`.

## Not in scope (deliberately)

- **`session_id` batch grouping wired through the harness.** The *seam* supports
  it (`trace_attributes(session_id=…)`); actually grouping every eval batch into a
  Session is a clean, separate change to the harness loop — left as the next
  follow-up rather than smuggled in here.
- **LiteLLM's native Langfuse callback.** The skill prefers framework
  integrations, but our manual `generate` generation already captures
  model/tokens/cost and keeps prompts/PII off the trace deliberately; switching is
  a deeper trade-off, not a baseline fix.

## Issues

- `issue-1-langfuse-tracing-best-practices.md` — [#94](https://github.com/chiajung-wang/nl2sql-eval/issues/94) — the audit + the five deliverables above (single cohesive slice).
