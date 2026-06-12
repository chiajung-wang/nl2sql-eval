# Issue 2 — Technical blog post (every number links to its committed run)

**Type:** AFK
**Phase:** Step 10 (Amplification) — *Polish & reach* · **Non-negotiable**

## Parent

`docs/plans/step-10/plan-step-10.md`

## What to build

The **technical blog post** that narrates the eval-centric value a quick demo glance won't convey.

Suggested structure:
- The inversion: why the wrapper is the product.
- How I know my evaluator is correct (the golden fixture).
- What self-correction is worth (pass@1→pass@k, with cost).
- What retrieval is worth (naive baseline → retrieval lift; retrieval-recall for the silent failure).
- Deterministic guardrails + red-team catch rate.
- Operating it: tracing, redacted-logging, prompt-CI catching regressions.
- Honest limits (single-db scope; silent retrieval failures measured not fixed).

**Every number links to its committed run** — the rigor is the story.

## Acceptance criteria

- [ ] Blog post narrates the eval-centric thesis end-to-end (inversion → comparator → correction → retrieval → guardrails → operations → limits)
- [ ] Every reported number links to its `RESULTS.md` entry / commit
- [ ] Honest-limits section is present (single-db scope; silent retrieval failures measured not fixed)
- [ ] Published (or publish-ready) in `docs/blogs/`

## Blocked by

- [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60) — the README; and the full `RESULTS.md` trail.

---

## Tracking

**GitHub:** [#61](https://github.com/chiajung-wang/nl2sql-eval/issues/61) · label `agent-ready`, `step-10`

**PR:** _pending_

**Blocked by (GitHub):** [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60)

**Step 10 set:** [#60](https://github.com/chiajung-wang/nl2sql-eval/issues/60) · [#61](https://github.com/chiajung-wang/nl2sql-eval/issues/61) · [#62](https://github.com/chiajung-wang/nl2sql-eval/issues/62) · [#63](https://github.com/chiajung-wang/nl2sql-eval/issues/63) (#63 optional reach)
