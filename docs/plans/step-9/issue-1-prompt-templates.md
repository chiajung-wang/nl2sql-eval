# Issue 1 — Prompt templates as clean version-controlled Jinja

**Type:** AFK
**Phase:** Step 9 (Operations) — *Prompt-CI/CD, the senior differentiator*

## Parent

`docs/plans/step-9/plan-step-9.md`

## What to build

The Step 9 foundation: make the externalized prompts **clean, version-controlled Jinja-style templates** so CI diffs stay legible.

- Ensure every prompt in `prompts/` is a Jinja-style template with explicit variable substitution for injected schema / few-shots (no inlined prompt strings in Python — CLAUDE.md §4).
- Structure templates so the static scaffold stays put and only meaningful edits show in a diff (keeps CI deltas clean).
- A prompt-version identifier is surfaced so `RESULTS.md` rows and CI runs can pin the exact prompt version.

## Acceptance criteria

- [ ] All prompts live in `prompts/` as Jinja-style templates with variable substitution; none inlined in Python
- [ ] Template structure isolates meaningful edits from static scaffold (clean diffs)
- [ ] A prompt-version identifier is surfaced and usable by the harness/RESULTS.md
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- A batch-capable, repeatable harness (Step 3) and a frozen/seeded/stratified slice (Steps 3 & 6). Direct predecessor: [#56](https://github.com/chiajung-wang/nl2sql-eval/issues/56).

---

## Tracking

**GitHub:** [#57](https://github.com/chiajung-wang/nl2sql-eval/issues/57) · label `agent-ready`, `step-9`

**PR:** _pending_

**Blocked by (GitHub):** [#56](https://github.com/chiajung-wang/nl2sql-eval/issues/56) (Steps 1–8 complete)

**Step 9 set:** [#57](https://github.com/chiajung-wang/nl2sql-eval/issues/57) · [#58](https://github.com/chiajung-wang/nl2sql-eval/issues/58) · [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59)
