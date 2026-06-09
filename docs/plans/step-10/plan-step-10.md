# Plan — Step 10: Polish & reach

**Phase:** Amplification
**Headline:** Make the project legible — and assemble the blog from the trail of committed results.

## Goal
Make the project readable to a reviewer and tell its story. **Split** the work by risk: README + blog post are **non-negotiable**; BigQuery is an **optional reach** that must never block the parts that make the project legible.

## Prerequisites
- Steps 1–9. Critically, the **`RESULTS.md` trail** built up from Step 3 onward — the blog assembles from it.

## What to build

### Non-negotiable
1. **README** — the portfolio front door. Lead with the thesis ("rigorous evaluation and operation of an LLM system"), the architecture diagram, the headline findings (pass@1→pass@k gap, naive→retrieval lift, red-team catch rate, cross-provider table), how to run it, and links from each claim to its `RESULTS.md` entry/commit.
2. **Technical blog post** — narrates the eval-centric value that a quick demo glance won't convey. Structure suggestion:
   - The inversion: why the wrapper is the product.
   - How I know my evaluator is correct (the golden fixture).
   - What self-correction is worth (pass@1→pass@k, with cost).
   - What retrieval is worth (naive baseline → retrieval lift; retrieval-recall for the silent failure).
   - Deterministic guardrails + red-team catch rate.
   - Operating it: tracing, redacted-logging, prompt-CI catching regressions.
   - Honest limits (single-db scope; silent retrieval failures measured not fixed).
   - **Every number links to its committed run** — the rigor is the story.
3. **Thin demo UI** (`apps/demo/`, Streamlit, isolated dep group) — must **reveal the wrapper**: show the guardrail decision, retry count, cost, terminal state — not hide a chatbot. Isolate deps so it can't conflict with the pipeline core.

### Optional reach (must not block the above)
4. **BigQuery connection** — the cloud-warehouse checkbox via sqlglot transpilation. Real integration risk (auth, dialect quirks, cost surprises). If it slips, ship without it; an unreadable repo is fatal, a missing cloud checkbox is not.

## Done when
- **Non-negotiable:** repo is open-sourced with a clean README, and the blog post is published, every claim traceable to `RESULTS.md`.
- **Reach:** BigQuery connected (if it didn't introduce blocking risk).

## Results log
This step *consumes* `RESULTS.md` rather than adding metrics — but record that the blog/README are published and add the BigQuery result if completed.

## Pitfalls
- Don't let BigQuery's integration risk delay the README/blog — they're what make everything else legible.
- The blog writes itself **only if** the results log was kept honestly from Step 3; if you skipped entries, you'll be reconstructing numbers from memory (the exact failure this discipline prevents).
- Keep the demo honest — revealing the machinery is the point; a slick chatbot that hides the wrapper undersells the project.
