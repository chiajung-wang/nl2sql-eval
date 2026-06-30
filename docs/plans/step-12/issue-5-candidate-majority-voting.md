# Issue 5 — Candidate diversity + result-set majority voting

**Type:** AFK
**Phase:** Step 12 (Optimization) — *the comparator, repurposed from gold-scoring to candidate selection*

## Parent

`docs/plans/step-12/plan-step-12.md` — source: Shkapenyuk et al., arXiv:2505.19988v2, §4.

## Motivation

The paper's submission generates **multiple candidates** and selects one by **majority voting on executed result-sets**: it produces 3 candidates (introducing diversity by (a) varying the LLM seed and (b) **randomizing the order of the schema-linked fields** in the prompt), executes each, converts results to sets, and if two agree, picks one; else picks randomly.

This maps cleanly onto two things we already have:
- **Our comparator** (`eval/compare.py`) *is* the result-set equivalence their voting needs — including the BIRD set-semantics handling. Voting is the comparator applied to *candidate selection* rather than *gold scoring*. We reuse the proven core, we don't rebuild it.
- **The pass@1 → pass@k gap** (PRD rule 6) is the metric this lever exists to move. Step 5 already studied self-correction's contribution to that gap; majority voting is a *different* selector over the same multi-candidate budget — a natural companion study.

The honest framing from Step 5 applies: a strong generator may produce candidates that already agree (vote is a no-op) — so an honest null is a legitimate outcome, and the *interesting* result is **where** voting beats taking attempt-1 (likely the weaker generators, as the self-correction twin found).

## What to build

- A **candidate-selection** step that generates k candidates with the paper's two diversity levers (seed variation + schema-field-order randomization), executes each, and selects by **result-set majority vote** using `eval/compare.py`'s equivalence (reused, not forked).
- Tie/no-majority policy: documented and deterministic-seeded (the paper picks randomly; prefer a deterministic tiebreak — e.g. first candidate, or lowest guard-cost — so runs are reproducible per §9 repeatability).
- This consumes the same multi-generation budget as self-correction; keep the two selectors **comparable**: report majority-vote vs attempt-1 vs the existing self-correct loop on the same k.

Constraints (CLAUDE.md §3/§5/§7):
- Voting reuses the **deterministic comparator** — no new SQL-equivalence logic, no string-match, no LLM judge (§7).
- Stays within the **capped budget** (§5); k candidates is the budget, not a bypass.
- **Scoring boundary:** the harness still scores the *selected raw verified result* against gold **upstream of redaction** (§3/§5). Voting selects a candidate; it does not change what or where we score.
- Import-shared; the demo selects the same candidate the harness scores (no drift).

## Evaluation protocol

- On dev, report the twin **pass@1 (attempt-1) vs pass@k (majority-selected)** for the same k, on **both** a strong generator (`accuracy` config) and a weaker one — mirroring the Step-5 twin's strong/weak contrast, because that's where the lever's value lives.
- Report the **vote-agreement distribution** (how often 3/3, 2/3, 0 majority) — the diagnostic that explains the gap (a strong model's candidates mostly agree → small gap).
- Report **cost**: k× generations + k executions, tokens, wall-clock — value with its price.
- Compare against the existing self-correct selector at the same budget: is majority voting additive, redundant, or worse? State it plainly.
- This lever's result is a **gap measurement**, not necessarily a headline pass@1 win — an honest null (strong model, candidates agree, +0.000) is an acceptable, expected outcome and is itself the finding.

## Acceptance criteria

- [ ] Candidate generation with seed + schema-field-order diversity; k within the capped budget
- [ ] Majority-vote selection reusing `eval/compare.py` result-set equivalence (no new equivalence logic, no string-match/LLM judge)
- [ ] Deterministic, documented tie/no-majority policy (reproducible per §9)
- [ ] Scoring stays upstream of redaction on the selected raw result; demo and harness select identically (import-shared)
- [ ] Twin **pass@1 vs pass@k (majority)** reported for strong **and** weak generator on dev; vote-agreement distribution reported
- [ ] k× generation/execution cost reported; comparison to the self-correct selector at the same budget stated
- [ ] Numbers in `RESULTS.md` with full config + commit
- [ ] `uv run pytest` green (voting/tiebreak unit-tested offline on recorded candidate result-sets); lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])** voting logic is offline-testable on recorded result-sets now; the live twin refreshes on an authorized key

## Out of scope

- The intermediate generations in `issue-1` (those are for *schema linking*, not answer voting) — though the two may share multi-generation plumbing.
- The paper's bad-construction pre-checks (`issue-2`) that gate candidates before voting — separate lever; they compose but are measured independently.
- Any change to the gold-scoring path or the comparator's verdict logic — voting *reuses* it read-only.

## Blocked by

- None hard. Composes with `issue-2` (gate candidates) and `issue-1` (better-linked candidates) but is independently measurable. Benefits from #133's wider slice to resolve the gap above the noise floor.

---

## Tracking

**GitHub:** [#142](https://github.com/chiajung-wang/nl2sql-eval/issues/142) · labels `agent-ready`, `step-12`

**PR:** _pending_

**Step 12 set:** #138 (task-alignment linking) · #139 (bad-construction guards) · #140 (profiling metadata) · #141 (literal→field) · **#142 (this)**
