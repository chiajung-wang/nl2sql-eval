---
title: "Step 1 — Proving the Machine Runs"
subtitle: "Building the thinnest honest NL-to-SQL loop, and the scaffolding that makes it measurable"
series: "nl2sql-eval: a case study in evaluating an LLM system"
part: 1
date: 2026-06-10
author: Chia-Jung Wang
tags: [llm, nl2sql, evaluation, postgres, sqlglot, architecture]
---

# Step 1 — Proving the Machine Runs

> **The premise of this project:** the NL-to-SQL agent is the *workload*; the eval
> harness, observability, and prompt-CI wrapper around it are the *product*. We
> build the measurement apparatus before the features. This post is about Step 1,
> where there are almost no features yet — and that's the point.

Most "text-to-SQL" demos open with a slick query and a correct answer. They are
impossible to trust, because nothing in the demo tells you how often the next
query is wrong, *why* it's wrong, or what would happen if the model emitted
`DROP TABLE`. The interesting engineering is not the generation — it's the
apparatus that turns a fallible LLM into something you can operate with a known
failure profile.

So Step 1 builds the *least* impressive thing on purpose: a hand-rolled
`question → SQL → execute → result` loop with no guardrails, no retrieval, no
self-correction, and no framework. The goal is a single sentence:

> **Prove the machine runs end-to-end** — one verified question goes in, a correct
> result comes out, and every architectural seam the later steps need is already
> in place (and empty).

The discipline is in what we *didn't* build, and in the shape of what we did.

---

## The thinnest loop

The whole pipeline is three stages wired linearly. No conditional edges, no retry,
no orchestration framework:

```python
# src/nl2sql/pipeline/graph.py
def run_pipeline(question, *, schema, engine, db_id="payments", ...) -> RunState:
    with stage_span("pipeline", db_id=db_id):
        state = RunState(question=question, db_id=db_id)
        generate(state, schema, model=model, client=client)
        execute(state, engine)
        return state
```

`generate` makes exactly one direct Anthropic call. `execute` runs the SQL through
SQLAlchemy. `graph` threads a mutable `RunState` between them and returns it. That's
the entire agent at Step 1. It is deliberately boring.

But notice four things that are *not* boring, because they're decisions that pay
off for the next nine steps.

### 1. The pipeline is import-shared, by contract

`run_pipeline` takes the schema text and the SQLAlchemy `Engine` as **arguments**.
It imports nothing from the dataset packages or the eval layer. That's not an
accident — it's the rule that lets the eval harness *and* the demo UI call the
exact same function:

> The pipeline is import-shared. Both `eval/harness.py` and `apps/demo/` import the
> *same* pipeline. Never fork or duplicate pipeline logic for the demo — no drift
> between what is demoed and what is measured.

If the thing you measure and the thing you demo can drift, your eval is a lie. We
enforce that structurally on day one, while the cost of doing so is zero.

### 2. The full terminal-state enum exists, even though most states are unreachable

Every run must bucket into exactly one terminal state. We define **all six** now,
in `state.py`, even though Step 1 can only ever reach two:

```python
# src/nl2sql/pipeline/state.py
class TerminalState(StrEnum):
    SUCCESS = "success"
    WRONG_ANSWER = "wrong_answer"            # needs the Step-2 comparator
    RETRY_EXHAUSTED = "retry_exhausted"      # needs the Step-5 correction loop
    EXECUTION_ERROR_FINAL = "execution_error_final"
    GUARDRAIL_REJECTED = "guardrail_rejected"  # needs Step-4 guardrails
    RETRIEVAL_EMPTY = "retrieval_empty"        # needs Step-6 retrieval
```

Defining the vocabulary up front means later steps add *reachability*, not
*reshaping*. `state.py` never churns.

### 3. The classifier lives in the harness, not in `state.py`

This is subtle and it's a hard rule. `state.py` holds the enum — the *vocabulary*.
The function that decides *which* state a finished run landed in lives in
`eval/harness.py`:

```python
# eval/harness.py
def classify_terminal_state(state: RunState) -> TerminalState:
    if state.error is not None:
        return TerminalState.EXECUTION_ERROR_FINAL
    return TerminalState.SUCCESS
```

Why separate them? Because classification is a *measurement* concern — it's the
harness's judgment about a run, and it will grow to depend on the comparator, the
guardrail verdict, and the retry budget. The pipeline state shouldn't know how it's
being judged. Keeping the classifier out of `state.py` keeps the workload ignorant
of the product measuring it.

> **A Step-1 honesty caveat** we documented in the code: a *generation* gap (the
> model emits no SQL) currently also buckets as `execution_error_final`, because
> `generate` is the only upstream stage and has no retry budget yet. When
> self-correction lands in Step 5, that splits out into its own state. Writing the
> caveat down beats letting a future reader mistake it for a bug.

### 4. The observability seam is wired now, and it's empty on purpose

Every stage is wrapped in a `stage_span` context manager that logs start/end and
duration. Today it emits structured logs and nothing else — it is *not* wired to
Langfuse (that's Step 8). Instrument-as-you-build:

```python
# src/nl2sql/obs/__init__.py
@contextmanager
def stage_span(stage: str, **fields):
    start = time.perf_counter()
    log_stage(stage, event="start", **fields)
    try:
        yield extra            # caller attaches *safe* fields here
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        log_stage(stage, event="end", duration_ms=duration_ms, **extra)
```

The seam carries a contract from birth: **only redacted/safe fields flow through
it.** The `execute` stage attaches `row_count` and `column_count` to the span —
**never the rows**, because the raw result set can carry PII. The raw rows live on
the `RunState` for upstream scoring; only the shape is ever logged. That separation
— raw result for scoring, redacted result for logs — is the spine of Steps 5 and 8,
and we pay for it now while it's a one-liner.

---

## Prompts are files, not strings

The generate stage loads its prompt from a version-controlled Jinja template, not
an inline Python string:

```jinja
{# prompts/generate/v1.jinja #}
You are an expert data analyst who writes PostgreSQL queries.
...
Rules:
- Return ONLY the SQL query — no prose, no explanation, no markdown code fences.
- The query must be read-only: a single SELECT statement.
...
Database schema (PostgreSQL):
{{ schema }}

Question:
{{ question }}
```

Prompts live under `prompts/` so CI can diff them, the version is in the filename
(`v1.jinja` → bump to `v2` for any change), and a reported eval number can be tied
to the exact prompt that produced it. A prompt is a parameter of the system, not a
literal buried in code.

One nuance worth calling out: the model is *told* not to use markdown fences, but we
still strip a fence defensively if it appears. That stripping is **presentation
only** — it is explicitly *not* SQL parsing. Semantic SQL handling (write detection,
table-scope checks) is sqlglot's job downstream in the guard stage, and the project
bans regex for SQL semantics. Unwrapping a code fence is not understanding SQL.

---

## The trusted ground: a verified seed set

You cannot measure accuracy without answers you trust more than the model. Step 1's
companion is a small set of hand-authored payments questions, each carrying both a
gold SQL query *and* a gold result set, verified against the seeded database:

```python
# eval/datasets/payments/questions.py
def load_questions() -> list[dict]:
    """Each record carries gold_sql + gold_result, verified against the seed."""
```

These are the trusted ground that Step 3 will validate the *harness* against before
we ever point it at the BIRD benchmark. If the harness can't correctly score
questions whose answers we know cold, it has no business scoring questions we don't.

### Why the gold check ignores column aliases

Here's where the centerpiece thesis bites. The live model answered "how many users
are in the US?" correctly — the value `3` — but it labeled the column
`us_user_count` where our gold labeled it `n`. An exact match on the result,
including column names, would have **rejected a correct answer**.

That's the single most important trap in NL-to-SQL evaluation, and it's domain rule
number one:

> Execution accuracy via canonicalized result-set comparison, **never SQL
> string-match.** Two different queries can be equally correct.

So the Step-1 gold check compares row *values* and ignores column aliases. It also
normalizes driver types — Postgres returns `SUM()` as a `Decimal`, while our gold
stores plain integer cents:

```python
# eval/prove_step1.py
def gold_matches(state, gold) -> bool:
    expected_rows = gold["gold_result"]["rows"]
    got_rows = [[_normalize(v) for v in row] for row in (state.result_rows or [])]
    return got_rows == expected_rows
```

This is a deliberate **stand-in**, and we labeled it as one in the code. The real,
canonicalized comparator — with order-insensitivity for unordered queries and fuller
type canonicalization — lands in `eval/compare.py` at Step 2, proven against a golden
fixture of `(gold, candidate, expected_verdict)` triples. We did *not* build a
competing comparator here; we built the smallest honest value-level check and pointed
at its successor.

---

## The proof

`eval/prove_step1.py` ties it together. It takes a verified seed question, runs it
through the *same* `run_pipeline` the harness and demo use, classifies the terminal
state, and asserts the result reproduces gold — exiting non-zero on a mismatch:

```
$ uv run python -m eval.prove_step1 pay-001

[pay-001] How many users are based in the United States (country code 'US')?
SQL:      SELECT count(*) AS us_user_count FROM users WHERE country = 'US'
columns:  ['us_user_count']
rows:     [(3,)]
terminal: success
PASS: result reproduces the verified gold answer (terminal success).
```

(The model's column alias `us_user_count` differs from gold's `n` — same value,
`3`. An exact-match comparator would have failed this correct answer.)

Live-proven against seeded Postgres with a real model:

| Question | Outcome |
|---|---|
| `pay-001` (count) | **PASS** — terminal `success` |
| `pay-004` (aggregation) | **PASS** |
| `pay-006` (join) | **PASS** |
| `pay-010` (documented gotcha) | value mismatch *surfaced* — model added `ORDER BY created_at`, got `23197` vs gold `23697` |
| deliberately bad SQL | terminal `execution_error_final` |

That `pay-010` row is the most valuable line in the table. The harness caught a
*wrong* answer that a string-match comparator might have waved through, and a
deliberately broken query bucketed cleanly into the error state. The apparatus
distinguishes right from wrong from broken. That is the entire job.

The deterministic pieces — the classifier and `gold_matches` — are covered by a
CI-safe unit test (`tests/test_terminal_classify.py`) that needs no database and no
network. The live run is the AFK proof; the unit test guards the logic underneath it.

---

## What we refused to build

Scope discipline is a feature. Step 1 explicitly kept out: sqlglot guardrails,
schema retrieval, the correction loop, LangGraph, LiteLLM, Langfuse integration, the
batch harness, and the demo UI. `sqlglot` is installed (it's stable) but not yet
used to guard anything.

And there is **no `RESULTS.md` entry.** Results-log discipline — every reported
number traceable to its model, slice, prompt version, date, and commit — starts at
Step 3, when the harness scores a frozen, seeded benchmark slice. Step 1 has nothing
to report but "it runs," and we don't dress that up as a metric.

---

## What's next

- **Step 2** — the real comparator in `eval/compare.py`: canonicalized,
  order-aware-where-it-matters result-set comparison, proven against a golden fixture.
  The Step-1 `gold_matches` retires into it.
- **Step 3** — the harness scores a frozen, seeded BIRD slice end-to-end, and the
  first real numbers land in `RESULTS.md`.

The machine runs. Now we build the thing that tells us how *well* it runs — which
was the product all along.
