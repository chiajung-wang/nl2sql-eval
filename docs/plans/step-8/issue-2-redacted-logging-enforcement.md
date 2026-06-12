# Issue 2 — Redacted-logging enforcement (raw PII never reaches traces)

**Type:** AFK
**Phase:** Step 8 (Operations) — *Observability + redacted-logging*

## Parent

`docs/plans/step-8/plan-step-8.md`

## What to build

Enforce the **redacted-logging discipline**: score upstream of redaction; log/present downstream of it. Traces and logs record the **redacted (presented)** result only — raw PII from the verified result must never reach Langfuse.

- Verify the two-exit discipline holds in the wired pipeline: the harness scores the *raw verified result*; redaction runs afterward; only the presented result is traced/logged.
- Add an assertion/test seam proving raw PII never appears in any span or log.

## Acceptance criteria

- [ ] The raw verified result is scored upstream of redaction; only the presented (redacted) result is traced/logged
- [ ] A test/assertion proves raw PII never reaches Langfuse spans or logs
- [ ] The two-exit discipline is verified in the wired pipeline (not assumed)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#54](https://github.com/chiajung-wang/nl2sql-eval/issues/54) — Langfuse span wiring.

---

## Tracking

**GitHub:** [#55](https://github.com/chiajung-wang/nl2sql-eval/issues/55) · label `agent-ready`, `step-8`

**PR:** _pending_

**Blocked by (GitHub):** [#54](https://github.com/chiajung-wang/nl2sql-eval/issues/54)

**Step 8 set:** [#54](https://github.com/chiajung-wang/nl2sql-eval/issues/54) · [#55](https://github.com/chiajung-wang/nl2sql-eval/issues/55) · [#56](https://github.com/chiajung-wang/nl2sql-eval/issues/56)
