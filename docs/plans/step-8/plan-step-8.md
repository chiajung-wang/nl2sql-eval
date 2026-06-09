# Plan — Step 8: Wire observability seams to Langfuse; enforce redacted-logging

**Phase:** Operations
**Headline:** Make any failure diagnosable from its trace — without ever logging raw PII.

## Goal
Wire the thin logging seams (added stage-by-stage during Steps 1–7) to **Langfuse**, and enforce **redacted-logging** discipline. Because the seams already exist, this is "connect and enforce," not "instrument seven steps from scratch" — honoring the instrument-as-you-build principle without front-loading the full obs layer.

## Prerequisites
- Steps 1–7, where each stage got a thin obs seam as it was built.

## What to build
1. **`obs/` → Langfuse** — wire each pipeline stage's existing seam to a Langfuse span; each run becomes a trace whose spans mirror the stages (`retrieve`, `generate`, `guard`, `execute`, `correct`, `redact`). Capture cost/latency/tokens natively (feeds the pass@1-vs-pass@k cost analysis).
2. **Redacted-logging enforcement** — the rule from the architecture pass: **score upstream of redaction; log/present downstream of it.** Traces and logs record the **redacted** (presented) result only — raw PII from the verified result must never reach Langfuse. Verify the two-exit discipline holds in the wired pipeline.
3. **Trace-driven debugging** — confirm you can open a failing question's trace and see, per span, what each stage did (retrieved tables, generated SQL, guard verdict, attempts, final terminal state).

## Done when
Any failing question is **diagnosable from its trace** — and no raw PII appears anywhere in logs/traces.

## Results log
Not a new accuracy number, but note in `RESULTS.md` that observability is wired and the redacted-logging discipline is verified. Capture a screenshot/example trace for the blog (great "operate the system" visual).

## Pitfalls
- The redacted-vs-raw exit discipline is a real production concern and a strong regulated-industry talking point — verify it actually holds, don't assume.
- Don't retrofit instrumentation from scratch; if a seam is missing from an earlier step, add the seam, then wire it.
