---
title: "Step 3 — The First Real Number"
subtitle: "Pointing the proven comparator at a frozen BIRD slice — and why the headline is 0.420, not a victory lap"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 3
date: 2026-06-11
author: Chia-Jung Wang
tags: [llm, nl2sql, evaluation, bird, pass@1, harness]
---

# Step 3 — The First Real Number

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness around it is the *product*. Step 1 proved the machine runs. Step 2 proved
> the scorer. Step 3 is the payoff of that order — we point the proven scorer at a
> real benchmark and read the dial. The number that comes back is **0.420**, and the
> most important thing about it is that we can defend every digit.

For two steps this project has refused to report an accuracy number. Not out of
modesty — out of discipline. A benchmark number from an unvalidated harness is the
flashy-but-shallow trap: it *looks* like progress and measures nothing. So we built
the pipeline first, then the comparator, then proved the comparator against a golden
fixture. Only now, with the instrument calibrated, do we get to take a reading.

Step 3 is **Phase 1's definition of done**: the project's thesis made concrete — a
*measured claim*, not a working toy. It comes in three slices, and the order is the
whole methodology.

---

## First, prove the harness on ground you trust

The temptation is to wire the harness straight to BIRD and watch numbers scroll. We
did the opposite. The first slice runs the batch harness against the **payments
gold set** — ~10 hand-authored questions whose answers we know cold — *before* a
single BIRD question is involved.

The logic is the same as the comparator's: if the harness can't correctly score
questions whose answers we trust, it has no business scoring questions we don't.

```python
# eval/harness.py (trimmed) — the loop the whole project rests on
for case in cases:
    state = run_one(case)                       # the SHARED pipeline, never a copy
    comparison, terminal = score_run(state, case)   # Step-2 comparator, upstream of redaction
    results.append(CaseResult(terminal_state=terminal, correct=..., note=...))
```

Two design rules earn their keep here. The runner is an **injected callable**, so
the harness logic runs offline in tests against canned `RunState`s — no DB, no
network — while the live job binds the same `run_pipeline` the demo uses. And the
**terminal-state classifier lives in the harness, not in the state object**: every
run buckets into exactly one of `success`, `wrong_answer`, or
`execution_error_final` (the rest of the taxonomy unlocks in later steps). The
classifier is a *measurement* decision, so it lives with the measurement apparatus.

The payments run lands at **pass@1 = 0.900 (9/10)** — and the single miss is the
most valuable line in the output. Question `pay-010`'s model answer adds an
`ORDER BY` that changes the returned value; the comparator scored it `wrong_answer`.
That's not a harness bug — it's the harness distinguishing *right* from *wrong* from
*broken* on data we trust. Exactly the precondition for trusting it on BIRD. (And
note: **no `RESULTS.md` entry** for payments. It's a self-check, not a reported
benchmark — numbers begin with the frozen slice.)

---

## Second, freeze the slice — seeded, stratified, committed

You cannot report a number against a moving target. So the BIRD slice is **frozen,
seeded, and stratified**, and the exact question-ID list is committed to the repo:

```jsonc
// eval/datasets/bird/slice_step3.json
{ "slice": "step3-naive-schema-dump-baseline",
  "criteria": { "max_tables": 5, "size": 50, "seed": 20260611 },
  "difficulty_mix": { "simple": 24, "moderate": 19, "challenging": 7 },
  "db_mix": { "thrombosis_prediction": 20, "toxicology": 14,
              "california_schools": 13, "debit_card_specializing": 3 },
  "question_ids": [6, 10, 12, 19, 20, 25, 32, 37, ...] }
```

Three choices, each deliberate:

- **Small-schema-first** (`max_tables ≤ 5`). The baseline dumps the *entire* schema
  into the prompt — no retrieval yet. Capping table count keeps that naive approach
  honest: the baseline measures *generation quality*, not the model drowning in a
  giant schema. Large-schema slices and schema-RAG are Step 6's job; conflating them
  now would muddy the very lift we want to measure later.
- **Seeded and stratified** (`seed = 20260611`). The 50 questions are a reproducible,
  difficulty-balanced draw — not the first 50, not a lucky 50. Re-run the sampler and
  you get the identical slice.
- **Committed ID list.** The slice is a *file*, not a procedure. Anyone can see
  exactly which questions produced the number.

This is repeatability as a feature, not an afterthought — and it's what makes the
prompt-CI of later steps possible: a frozen slice means a delta is a real
regression, not sampling noise.

---

## Third, mind the dialect — a bug the comparator would have hidden

BIRD is SQLite; the payments demo is PostgreSQL. The pipeline already threads a
`dialect` so the generate prompt asks for the right SQL flavor (and passes BIRD's
per-question *evidence* hint). But a subtler dialect bug lived in **scoring**.

Recall from Step 2 that order-sensitivity is gated on whether the *gold* SQL has a
top-level `ORDER BY`, detected by parsing the gold with sqlglot. BIRD's gold uses
SQLite idioms — backtick-quoted identifiers like ``ORDER BY `Avg Score` `` — that
the *generic* sqlglot parser rejects. A gold that fails to parse falls back to
order-insensitive… which means a genuine `ORDER BY` question could be silently
scored the lenient way.

The fix is one line of intent: parse the gold with the **SQLite dialect** (falling
back across dialects) so detection sees the real structure.

```python
# the gold is parsed dialect-aware, so ORDER BY detection isn't fooled by
# backtick-quoted BIRD identifiers the generic parser would choke on
_PARSE_DIALECTS = (None, "sqlite")
```

This is the kind of bug that never throws and never shows up as a crash — it just
quietly mis-scores a slice of questions. It surfaced only because the comparator's
behavior is *legible* and dialect handling is explicit. Measurement discipline isn't
glamorous; it's noticing that "it ran and produced a number" and "the number is
correct" are two different claims.

---

## The number — and what it is *not*

With the harness validated, the slice frozen, and scoring dialect-correct, the first
real reading lands:

| Date | Step | Metric | Number | Model | Slice | Prompt | Commit |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | 3 | pass@1 | **0.420 (21/50)** | claude-sonnet-4-6 | step3-naive-schema-dump-baseline | generate/v2 | `5d9d8ae` |

**pass@1 = 0.420.** Twenty-one of fifty BIRD questions answered correctly on the
first attempt. Here is what that number deliberately *is not*:

- **Not state-of-the-art, and not trying to be.** This is the *naive baseline*:
  whole-schema dump, one generation, no retrieval, no self-correction, no error
  feedback. It exists precisely so later steps have a floor to measure lift against.
  Step 5's self-correction will report the **pass@1 → pass@k gap**; Step 6's
  schema-RAG will report the **naive → retrieval lift**. You cannot quote a lift
  without a baseline, and this is the baseline.
- **Not just one number.** The harness reports pass@1, the **terminal-state mix**
  (how the 29 misses split between *wrong answer* and *execution error* — a genuine
  bad query is a different failure than a crash), and pass@1 *by difficulty*. The
  failure taxonomy is the analytical payload; the headline is just its first moment.
- **Not a remembered claim.** Every digit is traceable: model, slice ID, prompt
  version, date, and commit, committed to `RESULTS.md`. The eventual blog assembles
  from a trail of verified rows — it writes itself, and honestly.

---

## What we refused to build

Scope discipline, again, is a feature. Step 3 did **not**:

- **Tune the prompt to chase the number.** A baseline you've optimized is no longer
  a baseline. `generate/v2` is the honest naive prompt; its job is to be beaten,
  visibly, by features whose value we can then *quantify*.
- **Reach for the big-schema BIRD dbs.** Context-overflow effects would contaminate
  a generation-quality baseline. Big schemas arrive with the retrieval that makes
  them tractable (Step 6).
- **Add self-correction to nudge pass@1 up.** Retries would conflate "the model got
  it" with "the corrector saved it." pass@1 and pass@k are *twin* metrics for a
  reason; Step 5 introduces the retry loop and reports both.

---

## What's next

- **Step 4** — the first *measured feature*: deterministic guardrails (read-only,
  dangerous-op, cost) proven against a red-team fixture. A safety feature is only as
  good as the test that proves it works — so we report a catch rate, not a promise.
- **Step 5** — self-correction and the **pass@1 → pass@k gap**: how much is a retry
  budget actually worth?

Step 2 built the instrument and proved it. Step 3 pointed it at something real and
read the dial: **0.420**, traceable to the exact configuration that produced it.
It's a modest number — and it's a *trustworthy* one, which was always the point. The
dial is calibrated. Now we start adding the features whose worth it can measure.
