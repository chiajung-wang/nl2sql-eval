---
title: "Step 8, Follow-up — Letting the Tool Grade Its Own Wiring"
subtitle: "Step 8 wired Langfuse onto the pipeline. This follow-up installs Langfuse's own skill and runs its instrumentation audit over that wiring — which scored well, surfaced exactly one unmet baseline, and (once real keys went in) caught a silent blocker that would have dropped every trace on the floor. Then it groups each eval batch into one Langfuse Session."
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 8.5
date: 2026-06-18
author: Chia-Jung Wang
tags: [llm, nl2sql, langfuse, observability, tracing, pii, redaction, skills, evaluation, measurement]
---

# Step 8, Follow-up — Letting the Tool Grade Its Own Wiring

> **Where we left off.** Step 8 connected the pipeline's `obs/` seams to Langfuse —
> a span per stage, a trace per run — enforced the two-exit redaction contract, and
> proved a failing question is diagnosable from its trace, all without a live key.
> The mechanism was sound. But "I wired it carefully" is a claim, and the whole
> premise of this project is that claims about an LLM system should be *graded by an
> apparatus*, not asserted. So this follow-up does the obvious thing: it installs
> **Langfuse's own skill**, points its instrumentation audit at the Step-8 wiring,
> and fixes what the audit finds. The instrumentation passed most checks. It also
> had one real gap and one silent, embarrassing blocker — exactly the kind of thing
> a second pair of (automated) eyes is for.

There's a tidy symmetry here worth naming up front. The eval harness grades the
*model*. The red-team fixture grades the *guardrails*. A skill that audits your
instrumentation grades the *observability layer*. Same discipline, one level up:
don't trust that the thing you built is correct — run a check that can tell you it
isn't.

---

## Installing the auditor

The first move was to install the skill the way the project installs all its
skills — through the `skills` CLI, tracked locally:

```bash
npx skills add langfuse/skills --skill langfuse
```

The skill's first principle is one I appreciate: **documentation first.** Its
`SKILL.md` opens with "NEVER implement based on memory. Always fetch current docs
before writing code (Langfuse updates frequently)." Langfuse's Python SDK went from
v2 to v4 with real API churn — `update_current_trace` is deprecated, trace
attributes now flow through `propagate_attributes`, trace I/O is set on the root
observation directly. Coding any of that from memory would have produced
plausible-looking, subtly-wrong calls. So before touching a line I pulled the v4
docs and the v3→v4 migration notes. That single habit is the difference between
"works" and "works against the version you actually have installed."

Then I ran the skill's `instrumentation.md` baseline checklist against the wired
pipeline.

## The audit verdict

Most of it was already green, and I want to be honest that this is *because of
Step 8*, not in spite of it:

| baseline check | verdict |
|---|---|
| model name · tokens · cost | pass — on the `generate` generation span |
| span hierarchy · observation types | pass — `pipeline → retrieve → generate → guard → execute → correct → redact` |
| sensitive data masked | pass — shapes, counts, SQL; never result rows |
| `flush()` on exit | pass — the SDK self-registers an `atexit` shutdown |
| **trace input / output** | **gap** — the root span had no input and no output |

Two of those deserve a note.

The **`flush()`** row is a small vindication. The Step-8 `obs` docstring claimed
"`atexit` also flushes," and the skill lists "no `flush()` in scripts" as its #1
common mistake. So I checked the claim instead of trusting it — and Langfuse
v4.9's resource manager really does call `atexit.register(self.shutdown)`, and our
CLI entrypoints exit through `SystemExit`, which runs `atexit`. The docstring was
telling the truth. Good; but "I verified the claim" is the point, not "the claim
was right."

The **trace input/output** row is the genuine gap. Open a Step-8 trace and the root
`pipeline` span told you nothing — no question, no result. You had to drill into
child spans to learn what was even asked. The skill's checklist is blunt about why
that matters: a readable trace shows *meaningful input/output at the root*, "not all
function args." We had neither.

## Question in, result-shape out

The fix is to record, on the root span, the **NL question** as the trace input and
the **result shape** as the output. In v4 the root observation's I/O becomes the
trace's, so this is one `trace_input=` on the `pipeline` span plus a few safe fields
on the way out:

```python
extra["candidate_sql"] = run.candidate_sql
extra["presented_row_count"] = len(run.presented_rows or [])
extra["presented_column_count"] = len(run.presented_columns or [])
extra["attempts"] = run.attempts or 1
extra["guard_rejected"] = run.guard_rejected
```

There is a real judgment call buried in that first line, and it's the most
interesting thing in this whole follow-up. This project's prime directive is **raw
PII never reaches a trace** (CLAUDE.md §5.3). So is putting the *question* on the
trace a violation?

No — and the distinction is one worth being precise about. The redaction contract
protects PII that the system pulls *out of the database* into a result set. The
question is the user's own input message — the thing the skill explicitly names as
the canonical trace input. They are different data with different provenance. The
output I attach is read off the **presented (redacted)** exit and is only ever
*counts and shapes* — the row/column tally, the generated SQL, the attempt count,
the guard flag. Never a row. Scoring still happens upstream of redaction on the raw
result; the trace only ever sees what a user would. I wrote that reasoning into the
code comments rather than leaving it implicit, because "why is this safe?" is
exactly the question a reviewer in a regulated shop will ask.

While I was at the root span, I added the other thing the audit wanted — trace
identity — through a new offline-safe seam:

```python
with obs.trace_attributes(trace_name="nl2sql", tags=[f"db:{db_id}", f"model:{model}"]):
    with obs.stage_span("pipeline", trace_input=question, ...) as extra:
        ...
```

`trace_attributes` wraps v4's `propagate_attributes` — the *current* API, not the
deprecated one I'd have reached for from memory. It tags every trace with its db and
model so the cross-provider runs are filterable in the UI, and it accepts an
optional `session_id` for grouping a whole eval batch later. Like every seam in
this layer, it's a no-op when Langfuse is unconfigured and swallows any failure:
observability is a seam, never a dependency of a run.

## The silent blocker

Then I added real keys, and the audit's value compounded — because nothing
appeared.

This is the failure mode that makes observability maddening: no error, no trace,
just silence. The cause is a footgun the skill warns about explicitly. The Langfuse
**Python SDK** reads `LANGFUSE_HOST`. The **`langfuse-cli`** reads
`LANGFUSE_BASE_URL`. My `.env` — set up for the CLI — had only:

```
LANGFUSE_BASE_URL="https://jp.cloud.langfuse.com"
```

So `Langfuse()` never saw a host, silently defaulted to **EU cloud**, and my
**JP-region** keys failed to authenticate against the wrong region — quietly. No
amount of careful span wiring would have produced a single trace.

The fix makes the client robust to either variable, so the project's existing `.env`
just works:

```python
host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL")
return Langfuse(host=host) if host else Langfuse()
```

And to make this class of silent failure *loud* in the future, I added a smoke
verifier — `eval/langfuse_smoke.py` — that runs the real seam end to end:

```bash
uv run python -m eval.langfuse_smoke
# Langfuse smoke trace sent ✓
#   open: https://jp.cloud.langfuse.com/project/…/traces/707c9f1a…
```

It calls `auth_check` first (so bad creds or a wrong region fail *fast and
explained*, not silently), emits one trace through the actual `obs` seam, flushes,
and prints the URL. Offline, it reports "tracing disabled," sends nothing, and exits
non-zero. That run above is real: it authenticated against the JP project and
returned a live trace link — the host fix, confirmed end to end. Per the project's
defer-API-key discipline, the offline fake-recorder tests remain the source of truth
in CI; the live run is the one-time confirmation.

## The apparatus catches the author, again

Per the per-issue workflow, the change went through a two-axis review — Standards
and Spec, as parallel sub-agents — before merge. Both came back clean, but the
Standards axis flagged something fair: I'd added an explicit `obs.flush()` to two
batch entrypoints, while the README now claimed "any `eval.eval_*` run produces one
trace per question." Two out of seven isn't "any." The SDK's `atexit` covered
correctness everywhere, so nothing was *lost* — but the determinism rationale wasn't
applied uniformly, and the docs overstated. So the review fix wired `obs.flush()`
across all seven batch runners. A small thing, but it's the third or fourth time in
this series the apparatus has caught its own author rounding up; that it keeps
happening is the system working.

## The follow-up's follow-up: one batch, one Session

I'd called grouping eval batches under a `session_id` the "next follow-up" — and
rather than let it drift, I did it next, in the same step under the same discipline.
The seam from the trace-attributes work already accepted a `session_id`; the only
real question was *where* to set it. The wrong answer is to thread a run id through
`run_pipeline` and every stage. The right one, in v4, is a single line at the
harness — `propagate_attributes` applies to every child observation in scope, so
wrapping the batch loop is enough:

```python
with obs.trace_attributes(session_id=run_id):
    for case in cases:
        run_one(case)   # each question's pipeline trace inherits the session
```

No pipeline signature changed. A small helper builds a stable, readable id —
`<mode>:<model>:<prompt>:<UTC date>`, e.g.
`bird-rag-select:anthropic/claude-sonnet-4-6:v3:2026-06-18` — so a whole eval run is
one comparable unit in the Sessions view: same-day re-runs land together, and A/B
modes split into *sibling* sessions (`bird-rag-naive` vs `bird-rag-select`, one per
model on the cross-provider run, `:pass1` vs `:pass{k}` on the twin). All seven batch
entrypoints pass one; offline it's a pure no-op, like everything else in this layer.
That slice shipped as #96 / PR #98 through the same per-issue loop — including its
own clean two-axis review, whose single fix was deleting a dead variable the loop
refactor left behind. The apparatus, once more, doing its small honest job.

## What I deliberately did not do

One tempting thing stayed out of scope, on purpose:

- **Switching `generate` to LiteLLM's native Langfuse callback.** The skill prefers
  framework integrations over manual instrumentation, and in general that's right.
  But our manual generation already captures model, tokens, and cost, and it
  deliberately keeps prompts and PII off the trace. Swapping it is a real trade-off
  to weigh, not a baseline fix to rush.

Naming what you skipped, and why, is part of the same honesty the eval numbers are
for.

---

## The takeaway

Step 8 made the pipeline observable. This follow-up made me *confident* it was
observable — which is a different thing, and the difference is an audit I didn't run
myself. The skill scored the wiring, found the one root-level gap, and its own
documented footgun list pointed straight at the region/host mismatch that was
silently eating every trace. The fixes were small. The lesson isn't: it's that the
measurement discipline at the heart of this project doesn't stop at the model. You
can grade your guardrails, grade your retrieval, grade your costs — and grade the
instrumentation that lets you grade everything else.

*Artifacts: [PR #95](https://github.com/chiajung-wang/nl2sql-eval/pull/95)
([#94](https://github.com/chiajung-wang/nl2sql-eval/issues/94)) ·
[PR #98](https://github.com/chiajung-wang/nl2sql-eval/pull/98)
([#96](https://github.com/chiajung-wang/nl2sql-eval/issues/96)) ·
`docs/plans/step-8-follow-up/`.*
