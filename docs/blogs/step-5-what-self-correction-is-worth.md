---
title: "Step 5 — What Self-Correction Is Worth"
subtitle: "Turning the generator into an agent with a capped correction loop — then measuring the pass@1→pass@k gap rigorously enough to report that, here, it's zero"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 5
date: 2026-06-12
author: Chia-Jung Wang
tags: [llm, nl2sql, self-correction, pass-at-k, evaluation, agents, measurement]
---

# Step 5 — What Self-Correction Is Worth

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness and the apparatus around it are the *product*. Step 4 added the first
> measured feature — a safety gate — and proved it caught everything. Step 5 adds the
> feature everyone reaches for next — **self-correction** — and asks the question
> almost nobody asks: *what is it actually worth?* The answer, on this slice, is the
> most useful kind of number: **a gap of +0.000.** Self-correction recovers nothing
> here, and the whole point of Step 5 is that we can **prove** that rather than ship a
> retry loop and assume it helped.

Give an LLM a way to see its own errors and try again, and accuracy goes up. That's
the folk wisdom, and it's often true. It's also the most dangerous kind of feature to
add to a measured system, because it *looks* like it's working even when it isn't:
the loop quietly retries, eventually stumbles onto a passing answer on some question,
and the headline accuracy ticks up while latency and cost balloon out of sight. You
shipped a slot machine and called it an agent.

Step 5 builds self-correction — and builds the measurement that keeps it honest, in
that order. Two numbers, always together: **pass@1** (the single shot) and **pass@k**
(with the correction budget), plus the **cost and latency** the gap between them buys.

---

## The loop: from single-shot to agent, with a cap

Until now the pipeline was a straight line: `generate → guard → execute → return`.
One shot, one verdict. Step 5 closes the loop. When `execute` records an error, a new
`correct` stage captures the failed SQL and the database's error message, stages them
as feedback, and the graph regenerates — repeating until the candidate succeeds or a
**configurable, capped retry budget** is spent.

```python
# pipeline/graph.py — the capped correction loop
while True:
    state.attempts += 1
    generate(state, schema, ..., correction=state.correction)
    guard(state, dialect=dialect)
    if state.guard_rejected:
        return state                       # guard rejection is terminal here
    execute(state, engine)
    if state.error is None or state.attempts >= budget:
        return state                       # recovered, or budget spent
    correct(state)                         # stage the failure → regenerate
```

The cap is not an afterthought — it's the whole risk-management story. An uncapped
correction loop is an unbounded bill and an infinite hang waiting to happen.
`max_attempts=1` is the default (the single-shot pass@1 mode); a caller opts into a
budget, and that budget is an explicit cost/latency lever you get to discuss.

Two design rules carried over from earlier steps. First, **the feedback is data, not
prose**: `correct` assembles the prior SQL and error into a structured value; the
*wording* that frames it lives in the externalized prompt template
(`prompts/generate/v3.jinja`), under a `{% if correction %}` block. With correction
off, that template renders **byte-identical to v2** — so pass@1 cannot drift, a
property a fresh-agent review caught me getting subtly wrong (a stray trailing
newline) and made me fix before it shipped. Second, **the terminal-state classifier
stays in the harness**, never in the pipeline. The loop produces an `attempts` count;
the harness reads it to split a budget-exhausted failure (`RETRY_EXHAUSTED`) from a
single-shot one (`EXECUTION_ERROR_FINAL`).

**Scope, stated plainly:** this loop handles **execution-error feedback only**. The
other obvious correction signal — *re-retrieving* when a query references a table or
column that doesn't exist — is deferred to Step 6, because schema-RAG doesn't exist
yet. You cannot re-trigger a retrieval that isn't there. (This was a corrected
ordering bug in the plan itself; naming it is cheaper than pretending the loop does
more than it does.)

---

## The twin metric: never report the lift without its price

A loop that recovers errors is only worth what it costs to run. So the harness was
extended to report **both** numbers over the same slice — and to make the recovery
visible *against* its price:

- **pass@1** — the generator alone, no correction.
- **pass@k** — the same questions with the full correction budget.
- Per-question **attempts**, **tokens**, **latency** — and tokens turned into real
  dollars through a small, **dated** price table (a retry spends tokens twice; the
  cost accounting has to see that).

The gap between pass@1 and pass@k is the headline. The cost and latency beside it are
the guardrail against the slot-machine failure mode: a recovery that doubles latency
to claw back two points of accuracy is a *choice*, and you can only make it if the
number shows you the trade. The harness computes the gap directly rather than leaving
it to be reconstructed later — a finding you don't capture at the moment you produce
it is a finding you'll approximate from memory.

---

## The rigor problem: two runs measure noise, not correction

Here's where building the measurement apparatus earns its keep, because the obvious
way to get the twin metric is **wrong**.

The obvious way: run the slice once with correction off, once with correction on, and
diff the two accuracies. I built exactly that first. The problem is that an LLM is
**stochastic** — the two runs sample different first attempts. A question can flip
from wrong to right between the two passes purely because the model happened to draw a
better completion the second time, *with no correction involved at all*. The "gap"
you measure is then partly the value of self-correction and partly sampling noise, and
you cannot tell which is which.

This isn't hypothetical. A throwaway two-run pass on the slice reported a cheerful
**+0.060 gap** — while the loop's own counters showed only **one** correction had
actually fired. Two of those three "recovered" questions were resampling luck wearing
a correction costume. Ship that number and you've published noise as a finding.

The fix is the standard `pass@k` discipline: **derive both metrics from a single
run.** Run pass@k once, and read pass@1 off that same run's *first attempts*. The key
observation is that the correction loop only ever retries on an **execution error**,
so a run with more than one attempt is, necessarily, a run whose first attempt
errored:

```
pass@1-correct  ⟺  (final-correct  AND  attempts == 1)
```

A clean-but-wrong first attempt never retries (the loop returns on any successful
execution, right or wrong), and a guardrail rejection is terminal — so neither can
ever produce `attempts > 1`. That makes the derivation exact, not approximate, and it
was worth validating against the actual graph control flow in review rather than
trusting the prose. One run, zero cross-run noise, and the gap is precisely the set of
questions an attempt-1 execution error recovered from — nothing else.

```python
def derive_pass1_report(passk):
    # pass@1 = the first-attempt view of the SAME pass@k run
    for r in passk.results:
        first_attempt_correct = r.correct and r.attempts == 1
        ...
```

---

## The number: +0.000, and why that's the result

Run it over the frozen BIRD slice:

| Date | Step | Metric | Number | Model | Prompt | Commit |
|---|---|---|---|---|---|---|
| 2026-06-12 | 5 | pass@1→pass@3 | **0.420 (21/50) → 0.420 (21/50) [gap +0.000]** | `claude-sonnet-4-6` | `generate/v3` | `7ae5bb5` |

The gap is **zero**. Not a small positive — zero. And the breakdown says exactly why.
Of the 29 questions pass@1 got wrong:

- **0** were execution errors,
- **27** were wrong-answers (the SQL parsed, passed the guard, executed cleanly — and
  returned the wrong rows),
- **2** were guardrail rejections.

The correction loop **never fired**, because there was nothing for it to correct. On
this slice the model doesn't write *broken* SQL — it writes *wrong* SQL. The failures
are **semantic, not syntactic**, and execution-error self-correction is, by
construction, blind to them. There's no error message to feed back when the query runs
fine and just answers a different question than the one asked.

Two things make this a good result rather than a disappointing one.

First, it's the twin metric **earning its keep**. A naive harness would have run
pass@k, seen 0.420, and reported it as a feature working. The twin metric *proves* the
loop adds no accuracy here — it converts "we added self-correction" from an
unexamined claim into a measured zero. That is the entire thesis of this project in
one number.

Second, pass@1 came back at **exactly 0.420** — the same value as the Step-3 baseline.
That's the byte-identical-prompt property paying off: `generate/v3` renders the same
bytes as v2 when correction is off, so the single-shot accuracy is genuinely
comparable across two steps and three weeks of code change. And because pass@1 is
*derived from the same run* as pass@k with no retries firing, the cost and latency
delta isn't "small" — it's **exactly zero**. No second run, no variance, no asterisk.

---

## What we refused to build

- **Retrieval re-trigger.** Re-fetching schema on a not-found error is the *other*
  correction signal, and it's the one that would actually move a semantic-failure
  slice. It needs schema-RAG, which is Step 6. Building it now would mean Step 5's
  done-when secretly depended on Step 6's machinery.
- **A guardrail-feedback loop.** The seam is there — a guard rejection *could* become
  a correction signal instead of a hard stop — but it's out of scope until there's a
  reason and a test for it. The hook waits.
- **Two independent runs for the gap.** Tempting because it's simple; rejected because
  it measures sampling noise. The single-run derivation is more code and the correct
  code. (The two-run variant survives in the harness, clearly labelled as the
  *end-to-end cost-per-mode* tool it actually is — not the accuracy gap.)

---

## What's next

The Step-5 finding is also the Step-6 mandate. The failures on this slice are
semantic — the model retrieves the whole schema, dumps it into the prompt, and still
picks the wrong tables or columns. That's not a retry problem; it's a **retrieval and
grounding** problem.

- **Step 6** — schema-RAG: retrieve the *relevant* tables instead of dumping the whole
  schema, report **retrieval recall** against the gold query's actual tables, and
  measure the **naive → retrieval lift**. The loop-aware re-trigger (re-retrieve on
  not-found) finally lands too — the correction signal Step 5 deliberately left on the
  table. And the table-scope guardrail arrives with the per-db metadata that makes it
  real.

Step 4 proved a feature caught everything. Step 5 proved a feature catches *nothing* —
on this slice, for this failure mode — and that proving the zero is exactly as
valuable as proving the catch. The pattern holds: build the measurement that can tell
you the truth, then read the truth it tells you. Sometimes the truth is that the
shiny feature didn't help, and the apparatus that says so plainly is worth more than
the feature ever was.
