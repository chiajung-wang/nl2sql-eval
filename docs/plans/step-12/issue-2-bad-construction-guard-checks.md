# Issue 2 — Deterministic "bad-construction" checks as guard / correction signals

**Type:** AFK
**Phase:** Step 12 (Optimization) — *new deterministic checks in our existing guardrail shape*

## Parent

`docs/plans/step-12/plan-step-12.md` — source: Shkapenyuk et al., arXiv:2505.19988v2, §4.

## Motivation

The paper's BIRD submission runs a set of **deterministic, AST-detectable "bad SQL construction" checks** after generation and *before accepting* a candidate; on a hit it asks the model for a correction (up to 3 retries). These are not stylistic — each correlates with a *wrong answer*:

- **NULL-ordering hazard:** a `NULL` sorts before all values, so a query that is `ORDER BY f ASC` (taking the first row) or selects `min(f)` without a `NOT NULL` predicate on `f` silently returns a NULL-driven wrong answer. Check: require `f IS NOT NULL` when the result depends on ascending order / `min(f)`.
- **min/max via nested subquery instead of `ORDER BY … LIMIT`** — flagged as a likely-wrong shape.
- **String catenation of fields** instead of returning them individually — flagged as a likely-wrong projection shape.

This is *exactly* our guardrail shape (CLAUDE.md §4): deterministic **sqlglot-AST** checks, pre-execution, with the established **reject-or-feed-back-as-correction-signal** contract (`guard.py` → `correct.py`). Unlike the table-selection frontier (a model-capability wall, #122), these are concrete, mechanical defects a deterministic check *can* catch — making this the rare Step-12 lever with a clean, non-model-bound mechanism. It is also directly **measurable against a red-team-style fixture** (PRD rule 11), so the catch rate is a reported number, not a claim.

## What to build

New deterministic check(s) in `guard.py` (or a sibling "soundness" check group, if cost/dangerous/read-only grouping argues for it), each a **pure function over the sqlglot AST**:

- `null_ordering` — `min(f)` in the select list, or `ORDER BY f ASC` feeding a row-limited result, without a `NOT NULL` guard on `f`.
- `minmax_subquery` — min/max computed via a nested scalar subquery where `ORDER BY … LIMIT 1` is the idiomatic form (diagnostic-grade; tune to avoid false positives on genuine correlated subqueries).
- `field_catenation` — string concatenation of distinct fields in the select list where returning them separately is expected.

Wiring & boundary (CLAUDE.md §4/§7):
- These are **soundness signals**, not safety gates like read-only/dangerous-op. Decide per check whether a hit should **reject** or **feed back as a correction signal** — the paper feeds back; our `correct.py` loop already exists and is the natural home. Default to correction-signal (recoverable), not hard reject, so a false positive degrades to a retry, not a lost run.
- Each must stay inside the **capped retry budget** (§5) — no budget bypass.
- **No regex for SQL semantics, no LLM** in the check itself (§7). The correction *prompt* may be LLM-driven (that's `correct.py`'s job), but the *detection* is AST-only.
- Reuse `GuardResult` (rule/reason/note) so a hit is explainable and the terminal-state classifier can read it.

## Evaluation protocol

- **Fixture-first:** add `(query, expected_flag)` cases to a `fixtures/redteam_guard/`-style fixture (or a new `fixtures/soundness/` peer) covering each pattern + its near-miss negatives (a `min(f)` that *does* have `NOT NULL`; a legitimate correlated subquery). Report **catch rate** and **false-positive rate** on the fixture — this is the primary deliverable (rule 11), independent of any live run.
- **Live impact:** A/B on the dev slice — `accuracy` config with vs without the checks. Report pass@1 (strict + BIRD), and re-run `diagnose_bird` to show which buckets moved (expect movement in `where_mismatch` / projection / ordering buckets, *not* the table-selection cluster — be explicit that this lever targets a *different* bucket than `issue-1`).
- Report the **added retries** the correction feedback costs (as the Step-5 twin priced recovery).
- Honest-null clause: on the flash-class generators the precision buckets are already near-zero (#117), so the live lift may be ~0 even with a perfect fixture catch rate — that's an acceptable, documented outcome; the fixture catch rate is the durable result.

## Acceptance criteria

- [ ] New AST-only soundness check(s) in the guard layer, each a pure sqlglot function; reuse `GuardResult` for explainability
- [ ] Reject-vs-feed-back decided per check and documented; correction stays within the capped retry budget
- [ ] Soundness fixture added with positive + near-miss-negative cases; **catch rate and false-positive rate reported**
- [ ] Existing guard unit tests + red-team fixture still green (no regression to read-only/dangerous/cost/table-scope)
- [ ] Dev A/B pass@1 (strict + BIRD) with vs without the checks on the `accuracy` config; `diagnose_bird` bucket movement shown; added-retry cost reported
- [ ] Numbers in `RESULTS.md` with full config + commit
- [ ] `uv run pytest` green; lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])** the fixture proof is fully offline and is the primary deliverable; live A/B refreshes on an authorized key

## Out of scope

- The paper's *candidate selection* via majority voting (`issue-5`) — separate lever.
- Any LLM judge inside the *detection* (PRD §7); LLM use is confined to the existing `correct.py` correction prompt.
- Re-opening the FK-soundness corrector (#122, deferred as inside-noise-floor) — these checks target a *different*, mechanical defect class, not table selection.

## Blocked by

- None hard. Independent of `issue-1`/`issue-3`. Benefits from #133's wider slice for the live A/B but the fixture deliverable needs no slice.

---

## Tracking

**GitHub:** [#139](https://github.com/chiajung-wang/nl2sql-eval/issues/139) · labels `agent-ready`, `step-12`

**PR:** _pending_

**Step 12 set:** #138 (task-alignment linking) · **#139 (this)** · #140 (profiling metadata) · #141 (literal→field) · #142 (majority voting)
