# Issue 3 — Trace-driven debugging + RESULTS.md note (Step 8 DoD)

**Type:** AFK
**Phase:** Step 8 (Operations) — *Observability + redacted-logging* · **Step 8 Definition of Done**

## Parent

`docs/plans/step-8/plan-step-8.md`

## What to build

Prove **trace-driven debugging**: any failing question is diagnosable from its trace — and no raw PII appears anywhere.

- Open a failing question's trace and confirm you can see, per span, what each stage did (retrieved tables, generated SQL, guard verdict, attempts, final terminal state).
- Capture an example trace (screenshot/export) for the blog — a strong "operate the system" visual.
- Note in `RESULTS.md` that observability is wired and the redacted-logging discipline is verified (not a new accuracy number, but a recorded operational milestone).

## Acceptance criteria

- [ ] A failing question's trace shows per-span stage detail (retrieved tables, SQL, guard verdict, attempts, terminal state)
- [ ] An example trace is captured for the blog
- [ ] `RESULTS.md` notes observability wired + redacted-logging verified, with config + commit
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#55](https://github.com/chiajung-wang/nl2sql-eval/issues/55) — redacted-logging enforcement.

---

## Tracking

**GitHub:** [#56](https://github.com/chiajung-wang/nl2sql-eval/issues/56) · label `agent-ready`, `step-8`

**PR:** _pending_

**Blocked by (GitHub):** [#55](https://github.com/chiajung-wang/nl2sql-eval/issues/55)

**Step 8 set:** [#54](https://github.com/chiajung-wang/nl2sql-eval/issues/54) · [#55](https://github.com/chiajung-wang/nl2sql-eval/issues/55) · [#56](https://github.com/chiajung-wang/nl2sql-eval/issues/56)
