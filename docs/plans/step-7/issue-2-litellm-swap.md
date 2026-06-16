# Issue 2 — LiteLLM swap (multi-provider abstraction)

**Type:** AFK
**Phase:** Step 7 (Framework / provider) — *only AFTER logic is proven*

## Parent

`docs/plans/step-7/plan-step-7.md`

## What to build

Replace the direct single-provider LLM call with the **LiteLLM** abstraction (mirrors JKOPay's actual "LiteLLM Gateway" stack) so multi-provider comparison becomes trivial.

- Introduce an `llm/` boundary that routes generation/correction calls through LiteLLM.
- Default to the latest capable Claude models (Opus 4.x / Sonnet 4.x); other providers selectable via config.
- **Backends are selectable behind the LiteLLM boundary**: direct provider keys (`anthropic/claude-...`) *or* an aggregator via OpenRouter (`openrouter/...`) for one-key access to many models. OpenRouter is a *provider behind LiteLLM*, not a replacement — LiteLLM stays the boundary (CLAUDE.md §2, PRD §111/129 unchanged).
- Prove single-provider parity first: with the same model behind LiteLLM, the harness numbers match pre-swap.

> `generate.py` already takes an injectable `client`, so the boundary's wiring point exists. When an OpenRouter row feeds the frozen eval slice, pin its provider routing (`allow_fallbacks: false`) to keep runs repeatable (PRD §9).

## Acceptance criteria

- [ ] Generation/correction calls route through a LiteLLM `llm/` abstraction
- [ ] Provider/model is config-selectable; default is a latest-capable Claude model
- [ ] At least one alternate backend is reachable via the same boundary (a direct provider key and/or `openrouter/...`)
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
