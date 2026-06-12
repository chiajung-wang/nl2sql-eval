# Issue 2 — LiteLLM swap (multi-provider abstraction)

**Type:** AFK
**Phase:** Step 7 (Framework / provider) — *only AFTER logic is proven*

## Parent

`docs/plans/step-7/plan-step-7.md`

## What to build

Replace the direct single-provider LLM call with the **LiteLLM** abstraction (mirrors JKOPay's actual "LiteLLM Gateway" stack) so multi-provider comparison becomes trivial.

- Introduce an `llm/` boundary that routes generation/correction calls through LiteLLM.
- Default to the latest capable Claude models (Opus 4.x / Sonnet 4.x); other providers selectable via config.
- Prove single-provider parity first: with the same model behind LiteLLM, the harness numbers match pre-swap.

## Acceptance criteria

- [ ] Generation/correction calls route through a LiteLLM `llm/` abstraction
- [ ] Provider/model is config-selectable; default is a latest-capable Claude model
- [ ] Harness shows parity with the pre-swap direct call (same model, same numbers)
- [ ] `uv run pytest` green; lint/format clean

## Blocked by

- [#50](https://github.com/chiajung-wang/nl2sql-eval/issues/50) — the LangGraph refactor.

---

## Tracking

**GitHub:** [#51](https://github.com/chiajung-wang/nl2sql-eval/issues/51) · label `agent-ready`, `step-7`

**PR:** _pending_

**Blocked by (GitHub):** [#50](https://github.com/chiajung-wang/nl2sql-eval/issues/50)

**Step 7 set:** [#50](https://github.com/chiajung-wang/nl2sql-eval/issues/50) · [#51](https://github.com/chiajung-wang/nl2sql-eval/issues/51) · [#52](https://github.com/chiajung-wang/nl2sql-eval/issues/52)
