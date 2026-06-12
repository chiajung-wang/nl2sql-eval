# Per-issue workflow

The end-to-end loop for landing each `docs/plans/step-N/issue-*.md` issue. The
measurement apparatus is the product (PRD §1) — every slice ships as a
reviewable, self-documenting artifact, not just code. Follow these steps in
order for each issue; don't skip the review or the summary.

## The loop (per issue)

1. **Worktree.** Work in an isolated git worktree so the issue can't collide
   with other in-flight work.
2. **Implement.** Branch named `step-N/issue-<gh#>-<slug>`. Write the code per
   the issue's plan file. Honor the invariants in `CLAUDE.md` (prompts in
   `prompts/`, deterministic comparator/guardrails, module boundaries, etc.).
3. **Verify green.** `uv run pytest` + `ruff check` + `ruff format --check` all
   pass. If the issue produces an eval number, append it to `RESULTS.md` with
   its exact config (model, slice ID, prompt version, date, the number, the
   commit) — see `CLAUDE.md` §6.
4. **Commit → push → PR.** Open the PR with the base **explicitly `main`**
   (`gh pr create --base main`) — a wrong base silently strands merged work.
   Never add `Co-Authored-By: Claude` or "Generated with Claude Code" trailers
   (`CLAUDE.md` §7).
5. **Independent review.** Run the `/review` skill (Standards + Spec parallel
   sub-agents) against the branch since `origin/main`.
6. **Fix from review.** Commit a proportionate, genuinely actionable fix from
   the review findings — pick the real item, not a no-op.
7. **HTML summary.** Write `docs/plans/step-N/issue-<gh#>-summary.html` — a
   self-contained dark-theme page following the established template (hero
   badge, numbered `<h2>` sections, mermaid diagram, files-changed table,
   verification `.done` box). Mirror an existing
   `docs/plans/step-*/issue-*-summary.html` for the exact CSS/structure.

## After the step

8. **Next issue** → repeat 1–7.
9. **Step blog post.** Once every issue in the step has landed, write the
   Step-N blog post (under `docs/blogs/`). It assembles from the committed
   `RESULTS.md` entries and per-issue summaries, so every claim traces to a
   commit and config — the blog writes itself, honestly (PRD §10).
