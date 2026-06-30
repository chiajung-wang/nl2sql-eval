# Issue 3 — Profiling-derived field metadata (offline precompute)

**Type:** AFK
**Phase:** Step 12 (Optimization) — *the largest accuracy lever in the paper; the biggest build*

## Parent

`docs/plans/step-12/plan-step-12.md` — source: Shkapenyuk et al., arXiv:2505.19988v2, §2 / §2.1.

## Motivation

The paper's central, surprising result: **profiling-derived field metadata beats the human SME-supplied metadata** (MiniDev, no hints: profiling 61.2 vs supplied 59.6; fused best at 63.2). Their pipeline:

1. **Deterministic profile** per column: record count, NULL vs non-NULL, distinct count, value "shape" (min/max, length, character class, common prefixes), top-k sample values, optionally a minhash sketch.
2. **Mechanical English rendering** of the profile.
3. **LLM summarization** into a *short* description (for schema linking) and a *long* one (for SQL generation) — given the profile + table/column names as context.

It works because cryptic schemas hide format and meaning that profiling exposes: the paper's examples recover that `CDSCode` is a 14-char County-District-School id, that `Academic Year` is `'YYYY-YYYY'`, and that an undocumented `leadershipSkills` column is **JSON** — all read off the data, none in the supplied metadata.

This is the lever with the most accuracy headroom for us, because Step 11 ruled out the *cheaper* metadata moves (FK enrichment #112 was a null — the FKs were already in the DDL), but never tried **data-derived** field descriptions. It is also a clean **retrieval-lift** experiment (PRD rule 7): a new metadata source A/B'd against the naive and schema-RAG baselines.

## What to build

An **offline profiling precompute** + a metadata source the retrieve/generate stages can select:

- A deterministic profiler over each db's tables producing the per-column statistics above. SQLAlchemy executor (CLAUDE.md §2); BIRD/SQLite is the path, no EXPLAIN dependency.
- A **mechanical** profile→English renderer (no LLM — deterministic).
- An **LLM summarization** step producing short + long descriptions, run **once, offline, and cached** to a version-controlled artifact keyed by db + column. This is precompute, not a pipeline stage — the live pipeline reads the cache.
- A metadata-source selector so `retrieve.py`/`generate.py` can use: supplied-only (current), profiling-only, or **fused** (supplied + profiling, the paper's best), chosen via config.

Determinism boundary (CLAUDE.md §4/§7 — load-bearing):
- The LLM-summarized descriptions are **content for the generate prompt only**. They must **never** reach `guard.py` or `eval/compare.py` — those stay deterministic and data-independent. The summaries are precomputed and frozen, so a run is reproducible and scoring is untouched.
- The profile itself (the deterministic stats) may also feed `issue-4`'s value index; keep the profiling pass reusable.
- Cache is checked in and treated like a prompt artifact (version-controlled, diffable) — same discipline as `prompts/`.

## Evaluation protocol

- Retrieval-lift-style A/B on dev: **supplied-only vs profiling-only vs fused** metadata, on the `accuracy` config. Report pass@1 (strict + BIRD).
- Re-run `diagnose_bird` for bucket movement — expect movement where format/value errors live (`where_mismatch`, literal/format mismatches), and check whether richer field descriptions also help **table selection** (the paper's *short* summaries feed linking; pairs naturally with `issue-1`).
- **Prompt-size cost:** the long descriptions inflate the prompt — report token cost per question, and confirm the schema-linking lever (`issue-1`) keeps it bounded (the paper notes long-profile-for-every-field overflows context — that's *why* they built schema linking).
- Headline lift (or null) reported once on held-out.
- Cite the paper's parallel result honestly: profiling > supplied is *their* finding on GPT-4o/MiniDev; ours is an independent replication on our slice — report agreement or divergence plainly.

## Acceptance criteria

- [ ] Deterministic profiler over BIRD dbs producing per-column stats (counts, distinct, NULL, shape, top-k); SQLAlchemy executor
- [ ] Mechanical profile→English renderer (no LLM)
- [ ] Offline, cached LLM summarization (short + long); cache version-controlled and keyed by db+column; **never** read by guard/comparator
- [ ] Metadata-source selector (supplied / profiling / fused) wired into retrieve/generate via config; pipeline import-shared
- [ ] Dev A/B across the three sources on the `accuracy` config; pass@1 (strict + BIRD) + per-question prompt-token cost reported
- [ ] `diagnose_bird` bucket movement shown; held-out headline (or null) reported once
- [ ] Numbers in `RESULTS.md` with full config + commit
- [ ] `uv run pytest` green (profiler + renderer unit-tested on a fixture db); lint/format clean
- [ ] **(Deferred live runs, gated on key/spend — [[defer-api-key-verification]])** the profiler + renderer are fully offline/deterministic and testable now; the LLM summarization precompute + the A/B refresh on an authorized key

## Out of scope

- minhash-based join discovery (the paper uses sketches for join paths) — our join story is the FK graph (`enrich.py`); cross-table join *discovery* via sketches is a possible later extension, not this issue.
- The value/LSH index for literal matching — split into `issue-4` (it consumes this issue's profiling pass but is independently measurable).
- Query-log-derived metadata (paper §5) — non-goal for our benchmark (no logs in BIRD).

## Blocked by

- Independent, but largest build — sequence after `issue-1`/`issue-2` land if effort is constrained. Its profiling pass is a prerequisite for `issue-4`. Benefits from #133's wider slice for a less noisy lift.

---

## Tracking

**GitHub:** [#140](https://github.com/chiajung-wang/nl2sql-eval/issues/140) · labels `agent-ready`, `step-12`

**PR:** _pending_

**Step 12 set:** #138 (task-alignment linking) · #139 (bad-construction guards) · **#140 (this)** · #141 (literal→field) · #142 (majority voting)
