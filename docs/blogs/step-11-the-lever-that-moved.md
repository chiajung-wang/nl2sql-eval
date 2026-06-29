---
title: "Step 11 — The Lever That Moved (and the Three That Didn't)"
subtitle: "Pointing the finished apparatus back at the workload: the diagnostic turned 'pass@1 is 0.42, make it better' into a sequence of hypotheses the measurement adjudicated — schema enrichment (null), few-shot (subsumed), a model swap (+0.10), and a token-budget bug of our own that was hiding the strongest model (0.28 → 0.52)."
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 11
date: 2026-06-29
author: Chia-Jung Wang
tags: [llm, nl2sql, evaluation, error-analysis, optimization, reasoning-models, measurement, negative-results]
---

# Step 11 — The Lever That Moved (and the Three That Didn't)

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness and the apparatus around it are the *product*. Step 10 was the capstone — the
> demo and the public writeup. Step 11 is what you do *after* a measurement apparatus is
> finished: you point it back at the workload and actually try to make it better. The
> baseline had sat at **pass@1 0.420** since Step 3. "Make it better" is a vibe; this step
> turns it into a sequence of hypotheses, each one a lever the apparatus either confirms or
> kills. Three of the four obvious levers were nulls or subsumed. The one that moved
> accuracy was a model swap — and the biggest single jump came from discovering that our
> *own* token cap had been strangling the strongest model the whole time, dragging it from
> a fake **0.280** to a real **0.520**.

Every earlier step built a piece of the apparatus and proved it on demand. Step 11 is the
first step that *consumes* the whole thing for its actual purpose: optimization. And the
discipline that ran the series — don't optimize on vibes, make the measurement adjudicate —
turns out to matter most here, because optimization is exactly where wishful thinking
creeps in. You try a thing, the number wiggles inside the noise floor, and you convince
yourself it helped. The whole point of having a frozen slice, a twin metric, and a failure
taxonomy is to make that self-deception impossible.

---

## #111 — From a number to a map

`pass@1 0.420 (21/50)` means twenty-nine questions are wrong. A count is not actionable; a
*taxonomy* is. The first issue builds `eval/diagnose_bird.py`: it runs the frozen Step-3
slice once and, for every failure, emits the gold vs candidate SQL, the comparator's
reason, and a **deterministic, sqlglot-AST-derived tag** for the likely root cause —
missing join, wrong aggregate, table mismatch, extra `DISTINCT`, wrong projection width.
No regex for SQL semantics, no LLM judge: it diffs the two queries' structural feature
sets, it doesn't re-judge correctness (the comparator already did that, upstream of
redaction).

It also splits every failure into **scorer artifact vs genuine model error** by re-scoring
under BIRD's official set-semantics — separating "a query BIRD would accept that our
stricter multiset comparator rejected" from "the model is actually wrong." Only the latter
is worth fixing.

The map it drew set the entire agenda for the step: the dominant genuine-error buckets were
**wrong joins and wrong tables**, with a secondary cluster of **projection/distinct**
mistakes. Every lever below is a hypothesis aimed at a named bucket, and "did it work?" is
answered by re-running the diagnostic and checking whether *that bucket shrank* — not just
whether the headline twitched.

One more piece of discipline, added early: a **dev/held-out split**. Tune on the Step-3
dev slice; confirm any lift once on a disjoint, seeded, stratified 100-question held-out
slice. A prompt can memorize 50 questions' quirks; the held-out shot is the overfitting
insurance, and it's spent only on a lever that shows a dev lift.

---

## #112 — Schema enrichment: a clean null that located the failure

The obvious fix for "wrong joins" is to *show the model the join paths*. So: enrich the
schema dump with explicit foreign-key relationships and a few sample rows — same prompt,
same model, only the schema representation changes (a Step-6-style A/B, not a prompt edit).

It didn't work, and the way it didn't work is the useful part. Enriching with **both** FKs
and sample rows *regressed* pass@1 **0.420 → 0.340** and made the join bucket **worse**;
**FK-only** was flat (0.420 → 0.400, inside the noise floor) but nudged the target bucket
the right way. Read together: sample rows actively distract the generator, and surfacing
FKs barely helps — because **the foreign keys are already in the DDL the model sees.** These
aren't join-*discovery* errors (the model can't find the relationship); they're
join-*semantics* errors (it knows the tables and composes them wrong). Better representation
can't fix a query that already has the information and still gets it wrong. No held-out run
was spent — the protocol reserves that shot for a lever that earns it on dev, and this one
didn't. An honest null, and it narrowed the search.

---

## #113 and #117 — Few-shot gets subsumed; the model is the lever

The second bucket was projection/distinct precision, so the second lever was **few-shot
prompting**: a `v4` template with output-precision rules and three generic worked examples
(made up, drawn from *outside* every eval slice — the leakage rule a few-shot lever lives or
dies by). On the dev slice it moved its target buckets (`projection_count` 7 → 2,
`where` 4 → 1) and nudged the headline up.

But by the time it was built, the diagnostic had already pointed somewhere with far more
headroom: the **model**. Issue #117 made the generator selectable by a `MODEL` env var
(recorded in every `RESULTS.md` row, so a number always names what produced it) while
keeping the pinned default a direct, list-priced Claude model. With it, `gemini-3-flash`
scored **pass@1 0.500–0.540** on the same slice — a clean **+0.10** over the 0.420 baseline,
with *no* slice-overfitting risk because the model was never tuned on these questions.

And the diagnostic explained *why* gemini won: its projection/where buckets had already
collapsed to near-zero. Which is exactly the buckets the few-shot `v4` template targeted. So
**#113 was subsumed**: the precision lever buys almost nothing on a model that's already
precise. `v4` stays in the repo as a documented, tested negative result; `v3` remains the
active prompt. The honest call — recorded, not buried — is that a prompt tweak aimed at a
weakness the better model doesn't have is effort spent on the wrong axis.

A second model finding paid for itself immediately: `gemini-3.1-flash-lite` matches the
sonnet baseline (**0.420 / 0.460**) at roughly a twelfth the cost, with clean output. The
cheap dev workhorse and the accuracy pick are different models — and now both are one env
var away.

---

## #121, #125, #124 — The strongest model was hidden by our own cap

Then the most instructive episode of the step, because the bug was *ours*, not the model's.

Trying `gemini-3.5-flash` produced a dismal **pass@1 0.280** — worse than every other
model. The diagnostic refused to let that stand as a verdict: **25 of 50 candidates were
tagged `candidate_unparseable`** and rejected by the guard. The model is a *reasoning*
model; it wraps its SQL in chain-of-thought prose, and our extractor — anchored to unwrap a
reply that is *entirely* one fenced block — dropped the whole blob unparsed. **#121** made
`_extract_sql` robust: take the last fenced block anywhere in the reply, else the trailing
`SELECT`/`WITH`; presentation-only, sqlglot still validates downstream. Thirteen offline
unit cases, no spend to prove it.

It recovered a few — and then revealed the real culprit. Unparseable fell only 25 → 20, and
pass@1 stayed flat, because **30 of 50 calls were emitting ~1000 output tokens and hitting
our `MAX_TOKENS = 1024` cap, truncating mid-thought before any SQL appeared.** There was no
SQL to extract. A reasoning model spends its budget *thinking* first; a cap tuned for
non-reasoning models (sonnet emits ~70 tokens) was guillotining it. **#124** raised the
default to 4096 — a data-backed number, measured directly: gemini-3.5 finishes at
~1000–1150 tokens — and made it env-overridable. A no-op ceiling for non-reasoning models;
oxygen for reasoning ones.

The combined result turned the model completely around:

| `gemini-3.5-flash` (dev) | pass@1 strict / BIRD | `candidate_unparseable` | truncated |
|---|---|---|---|
| before (1024 cap, old extractor) | 0.280 / 0.300 | 25 | 30/50 |
| **after (4096 + robust extractor)** | **0.520 / 0.580** | **1** | **0** |

That makes `gemini-3.5-flash` the **top model on the slice** — above `gemini-3-flash`
(0.500/0.560) and the 0.420 baseline. The lesson is the uncomfortable kind: a reasoning
model was the strongest generator available *the entire time*, silently throttled by an
infrastructure default tuned for weaker ones. Not a model deficiency — a **measurement-
apparatus bug**. The apparatus diagnosing a flaw in the apparatus is this project's favorite
move, and here it was worth **+0.24**.

(One casualty along the way, fixed as **#125**: the diagnostic's re-scoring step
re-executes untrusted candidate SQL, and a truncated, garbled-but-parseable candidate
executed as a runaway query that *hung the whole run* — the `except` caught errors, not a
query that never returns. A SQLite progress-handler timeout bounds it now; a pathological
candidate is just another failure, never a hang. You find these exactly when you start
feeding the apparatus bad models on purpose.)

---

## #122 — The join/table frontier: a measured, model-bound limit

That left the original dominant bucket: wrong joins and wrong tables. Could a
**deterministic** lever touch it? To decide *before* building one, #122 sharpened the
diagnostic itself — decomposing the coarse cluster with sqlglot + each db's declared FK
graph into `spurious_join` (a join between FK-*unrelated* tables — the subset a soundness
check could flag), `missing_table`, and `extra_table`.

The decomposition was consistent across the baseline and the best model, and it killed the
deterministic lever before a dollar was spent on it:

| of the join/table failures | `spurious_join` | `missing_table` | `extra_table` |
|---|---|---|---|
| sonnet baseline (10) | 5 | 5 | 6 |
| gemini-3.5-flash (8) | 4 | 6 | 4 |

The FK-unsound `spurious_join` subset — the only part a deterministic guardrail could catch
— is a **minority**, and it overlaps with extra-table errors anyway (a spurious join usually
*is* a wrong extra table). The cluster is dominated by **table selection**: choosing the
wrong tables, or missing a needed one. Combined with #112's null (the FKs are already in the
DDL), the conclusion is firm: this is neither a representation problem nor an unsound-join
problem a checker can fix. It's a **model-capability frontier** — and the model swap is the
only thing that moved it (gemini-3.5 shrank the cluster 10 → 8 while everything else held).

So #122 ships the sharpened diagnostic and *declines* to wire a live correction signal: at
≤5/50 questions, a FK-soundness corrector's A/B would land inside the ~0.05 sampling-noise
floor — inconclusive by construction. Building it would be optimizing on a number we already
know we can't trust. Honest null on the accuracy lever; real gain on the apparatus.

---

## The number that matters: the gap, closed by the lever that earned it

| Date | Step | Lever | Number | Model | Slice | Commit |
|---|---|---|---|---|---|---|
| 2026-06-29 | 11 | schema enrichment | 0.420 → 0.340 / 0.400 (null) | sonnet | step3 dev | — |
| 2026-06-29 | 11 | few-shot `v4` | moves buckets, subsumed by model | sonnet | step3 dev | — |
| 2026-06-29 | 11 | **token budget + extractor** | **0.280 → 0.520 / 0.580** | `gemini-3.5-flash` | step3 dev | `352992e` |
| 2026-06-29 | 11 | join/table decomposition | spurious-join a minority; model-bound | sonnet · gemini-3.5 | step3 dev | `f935010` |

Every number traces to a model, a slice, and a commit in [`RESULTS.md`](../../RESULTS.md).
Reproduce the headline on the cheap dev workhorse or the accuracy pick:

```bash
MODEL=openrouter/google/gemini-3.5-flash uv run python -m eval.diagnose_bird   # 0.52, top model
MODEL=openrouter/google/gemini-3.1-flash-lite uv run python -m eval.diagnose_bird  # 0.42 at ~1/12 the cost
```

---

## What we refused to build

- **A schema enrichment we wanted to work.** Both-FK-and-samples regressed the headline;
  we recorded the regression instead of cherry-picking the FK-only variant that looked
  flat-to-positive. The null is the finding.
- **A few-shot prompt that the model made redundant.** `v4` moved its target buckets, but
  the better model had already zeroed them — so it stays a documented, tested negative
  result, not a shipped "improvement" defended by a dev number.
- **A deterministic join-soundness corrector.** The sharpened diagnostic proved it could
  reach at most a noisy-floor minority of the failures *before* we built it. The honest move
  is to measure the lever's ceiling first and not ship one whose A/B can't clear noise.
- **A new pinned default chasing the top score.** `gemini-3.5-flash` is the accuracy leader,
  but the pinned `DEFAULT_MODEL` stays a direct, list-priced Claude model — so the project's
  default doesn't depend on a third-party aggregator or forfeit clean cost accounting. The
  winners are *recommended overrides*, documented with their tradeoffs, not the pin.

---

## What's next

The honest verdict of Step 11 is that the apparatus is now better at finding the truth than
the workload is at improving: three of four levers were nulls or subsumed, and the real
gains came from a model swap and from fixing a budget bug that was hiding the best model.
The residual headroom — table selection on multi-table joins — is a model-capability
frontier this slice's deterministic and prompt levers can't reach. The next real movement
there comes from a stronger generator or a fundamentally different retrieval/grounding
approach, both of which the harness is now ready to adjudicate the moment they're tried.

The arc of this series was one idea applied over and over: build the thing that can tell you
the truth before you build the thing you hope is true. Step 5 proved a feature was worth
nothing; Step 6, that retrieval pays only where the schema overflows; Step 7, that a
framework swap changed exactly nothing; Step 9, that a prompt can't regress in silence
anymore. Step 11 closes the loop by turning the apparatus on the workload it was built to
measure — and the same discipline that made it trustworthy is what kept this step honest
about which levers were real. The measurement was always the product.
