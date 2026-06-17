---
title: "Step 8 — Diagnosable From Its Trace, Without Ever Logging PII"
subtitle: "Wiring Langfuse onto seams that were already there, enforcing the two-exit redaction contract, and proving a failing question is debuggable from its trace — all without a live key"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 8
date: 2026-06-17
author: Chia-Jung Wang
tags: [llm, nl2sql, langfuse, observability, pii, redaction, tracing, evaluation, measurement]
---

# Step 8 — Diagnosable From Its Trace, Without Ever Logging PII

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness and the apparatus around it are the *product*. By Step 7 the pipeline was
> framework-backed, multi-provider, and measured — but it wasn't observable from the
> outside. Step 8 makes it so: a **Langfuse span per stage, a trace per run**, the
> **redaction contract enforced** so only the presented (redacted) result is ever
> logged, and a proof that **any failing question is diagnosable from its trace** —
> with no raw PII anywhere. The honest twist: this whole step ships and is *proven*
> without a live Langfuse key, because the seams were built to be provable offline.

There is an easy version of "add observability" where you bolt a tracing SDK onto a
finished system at the end, discover the instrumentation points are all in the wrong
places, and quietly log a few things you shouldn't. Step 8 is the boring, correct
version instead — and it's boring precisely because of a decision made six steps ago.

---

## #54 — The seams were already there

Every stage of this pipeline has, since the step that built it, wrapped its work in a
thin `stage_span` context manager. For Steps 1–7 that seam did nothing but emit a
structured start/end log line with a duration. That was deliberate: **instrument as you
build**, so that when observability finally lands it's a *connect-and-enforce* job, not
a "go back and instrument seven stages from scratch" job.

So #54 is small, which is the point. `stage_span` now also opens a **Langfuse
observation** named after the stage. Nesting is automatic via Langfuse's
OpenTelemetry-backed context: the root `pipeline` span opens the trace, and every stage
span entered inside it becomes a child. One run becomes one trace whose spans mirror the
stages — `retrieve → generate → guard → execute → correct → redact`. The `generate`
stage opts into a `generation`-typed span so token usage and provider cost promote to
Langfuse's native `usage_details` / `cost_details` axes — the same cost basis the
cross-provider table reads, now also on the trace.

The part I care about most is what happens with **no key**:

```python
def get_client():
    # A live client only when BOTH Langfuse keys are set; otherwise None,
    # and stage_span degrades to exactly the prior structured-logging seam.
    ...
```

No keys → `get_client()` returns `None` → `stage_span` is the original log-only seam.
No network, nothing to mock, nothing that can break a run. This is the
[defer-API-key](#) discipline that runs through the whole project: implement now, prove
offline, defer the live run until a key exists. The wiring is proven against an injected
fake recorder; a missing or erroring Langfuse never surfaces as a pipeline failure.

A two-axis review nudged one real improvement here: a stage that *raises* now marks its
span `level="ERROR"` (with the exception **class**, never its message — a message can
echo query text) and re-raises. A failing run now shows *which* span failed. That single
change is what makes #56 possible.

---

## #55 — The two exits, made real

This is the invariant the whole project has been pointing at, and Step 8 is where it
stops being a comment and becomes enforced code. The pipeline has **two exits**:

- the **raw verified result** — what the harness scores against gold, *upstream* of
  redaction;
- the **presented result** — post-redaction, the *only* result the demo shows a user or
  that anything writes to logs and traces.

The `redact` stage produces the second from the first **without ever touching the
first**. Masking is *deterministic* (a fixed mask string, no LLM, no value-sniffing),
*column-aware* (it blanks the values of PII columns), and *schema-driven* — the PII
column set is parsed from the schema's own `-- PII` annotations:

```sql
email       TEXT NOT NULL UNIQUE,   -- PII   ← masked in the presented exit
brand       TEXT,                   -- e.g. visa (PII-adjacent)   ← not masked
```

The harness keeps scoring `result_rows` (the raw exit); `redact` writes only
`presented_rows`. Scoring stays upstream of redaction, and the masking can never corrupt
the verdict.

The plan was blunt about how to verify this — *"verify it actually holds, don't assume"*
— so the test is **non-vacuous on purpose**. It runs a real PII value through the full
pipeline, then asserts two things: that the run genuinely *read* the secret (it's in the
raw exit), and that the secret appears in **neither a Langfuse span nor a log line**. A
test that only checked absence could pass by never touching the data at all; this one
proves the data flowed and was still contained.

And an honest limitation, made conscious rather than hidden. Masking is by *output
column name*, so a PII column aliased to a non-PII name — `SELECT email AS contact` —
escapes. Closing that needs sqlglot projection resolution (output column → base column,
through aliases and `SELECT *`), which is deeper than this stage. So it's documented and
**pinned by a regression test**: a known trade-off with a test guarding the boundary,
not a silent hole. The project's whole posture is "honest limits over hopeful claims,"
and redaction is exactly where that posture has to be load-bearing.

---

## #56 — Diagnosable from its trace (and the key we didn't have)

The Step-8 "done when" is a sentence: *any failing question is diagnosable from its
trace, and no raw PII appears anywhere.* The catch: I don't have a live Langfuse key, so
I can't post a screenshot of the hosted UI. The deferred-key discipline says that's
fine — **prove it offline, in the same shape the live trace would take.**

`eval.prove_step8` drives a deliberately **failing** question — a query that always
references a missing column, so it parses (the guard allows it), executes, errors, and
exhausts its retry budget — through the *import-shared* `run_pipeline`. An in-process
`TraceRecorder` stands in for the Langfuse client, mirroring its
`start_as_current_observation` / `update` contract exactly, including the automatic
parent/child nesting. The captured trace is rendered to a self-contained HTML artifact
for the blog, and the recorder is contract-parity with the real seam — the same
`metadata`, `output`, `level`, and `usage_details` fields the live path writes.

Reading the captured trace top to bottom *is* the debugging session:

```
• pipeline
  • retrieve   tables=['orders', 'users']
  • generate   sql='SELECT user_id, COUNT(missing_col) FROM orders GROUP BY user_id'
  • guard      guard=allow
  • execute    error=OperationalError          ← attempt 1 fails
  • correct    corrected=True
  • retrieve   tables=['orders', 'users']       ← loop-aware re-retrieve
  • generate   sql='SELECT user_id, COUNT(missing_col) FROM orders GROUP BY user_id'
  • guard      guard=allow
  • execute    error=OperationalError          ← attempt 2 fails; budget spent
  • redact     presented=False                  ← nothing to present on a failed run
terminal: retry_exhausted  (attempts=2)
```

Every facet the criterion asks for is right there: which tables were retrieved, the SQL
each attempt generated, the guard verdict, the execution error (as the exception
*class*, so nothing leaks), the attempts, and — classified by the harness, never by the
pipeline — the terminal state. The terminal-state classifier stays in the harness; the
recorder only records. The `execute` and `generate` spans you'd scan first are flagged
red in the rendered artifact.

The review on this one earned its keep too: the script's defensive no-PII check was an
`assert`, which `python -O` strips. For a security-relevant gate that's a real footgun,
so it became a hard `raise`. Small fix, correct instinct — the apparatus reviewing its
own author again.

---

## What the results log records

Step 8 produces no new accuracy number — and the discipline is that a step still isn't
done until `RESULTS.md` says so, even when what it's recording is an *operational*
milestone:

| Date | Step | Metric | Model | Commit |
|---|---|---|---|---|
| 2026-06-17 | 8 | observability wired + redacted-logging verified | — (offline, fake client) | `a376fec` |

Observability wired (a span per stage, one trace per run, cost/latency/tokens native);
the two-exit redaction contract proven end-to-end (raw PII reaches neither span nor
log); a failing question diagnosable from its captured trace. Every claim traces to a
commit, and the offline proof reproduces with one command:
`uv run python -m eval.prove_step8`.

---

## What we refused to build

- **A live Langfuse screenshot, faked.** Without a key, the honest artifact is an
  offline capture in the *same shape* as the live trace — not a mocked-up image of a UI
  I didn't run. The recorder is contract-parity with the seam; the live trace is one key
  away, with no code change.
- **Value-level PII detection.** Redaction is schema-driven and column-aware on purpose —
  deterministic, explainable, no regex sniffing row contents, no model guessing what
  "looks like" an email. The aliasing gap that leaves is *documented and tested*, not
  papered over.
- **A from-scratch instrumentation pass.** The seams existed from Steps 1–7. Step 8
  connected them. If a seam had been missing we'd have added the seam and wired it — not
  retrofit the whole pipeline at the end, which is how observability usually rots.

---

## What's next

The system is now observable, and the redaction contract that lets a regulated shop
trust it is enforced and proven. The last piece of the apparatus is the one that makes
all of it *continuous*.

- **Step 9** — **prompt-CI/CD**: a GitHub Action that runs the harness on a frozen,
  seeded, stratified slice whenever a prompt changes, and posts the pass@1 / pass@k
  deltas on the PR. Every prior step built a measurement; Step 9 makes the measurement
  fire automatically, so a prompt change tells you — before merge — whether you improved
  or regressed.

Steps 5–7 each proved a sharp thing about *value*: a feature worth nothing, retrieval
that pays only on overflow, a refactor worth exactly zero behavioral change. Step 8 is
quieter and just as load-bearing: build the seams as you go, enforce the contract that
keeps raw data out of your logs, and make failure legible from the trace — so that when
something breaks in production, the answer is already on the screen, and the thing on the
screen never contains a customer's email.
