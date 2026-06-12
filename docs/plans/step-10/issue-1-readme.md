# Issue 1 — README: portfolio front door, every claim → RESULTS.md

**Type:** AFK
**Phase:** Step 10 (Amplification) — *Polish & reach* · **Non-negotiable**

## Parent

`docs/plans/step-10/plan-step-10.md`

## What to build

The portfolio front door: a **README** that makes the project legible to a reviewer in minutes.

- Lead with the thesis ("rigorous evaluation and operation of an LLM system").
- Show the architecture diagram (the instrumented state machine + the two pipeline exits).
- Surface the headline findings: pass@1→pass@k gap, naive→retrieval lift, red-team catch rate, cross-provider table.
- Explain how to run it.
- **Link every claim to its `RESULTS.md` entry / commit** — the rigor is the story.

## Acceptance criteria

- [ ] README leads with the thesis and the architecture diagram
- [ ] Headline findings surfaced (pass@1→pass@k, retrieval lift, red-team catch rate, cross-provider table)
- [ ] "How to run it" section is accurate against the real tooling
- [ ] Each headline claim links to its `RESULTS.md` entry / commit
- [ ] Markdown lints clean; links resolve

## Blocked by

- Steps 1–9, and the `RESULTS.md` trail they produced. Direct predecessor: [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59).

---

## Tracking

**GitHub:** [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60) · label `agent-ready`, `step-10`

**PR:** _pending_

**Blocked by (GitHub):** [#59](https://github.com/chiajung-wang/nl2sql-eval/issues/59) (Steps 1–9 complete)

**Step 10 set:** [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60) · [#61](https://github.com/chiajung-wang/nl2sql-eval/issues/61) · [#62](https://github.com/chiajung-wang/nl2sql-eval/issues/62) · [#63](https://github.com/chiajung-wang/nl2sql-eval/issues/63) (#63 optional reach)
