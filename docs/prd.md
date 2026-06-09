# PRD — Guardrailed Agentic NL-to-SQL Evaluation Harness

> A portfolio project whose thesis is **rigorous evaluation and operation of an LLM system**.
> The NL-to-SQL agent is the *workload*; the eval/observability/prompt-CI wrapper is the *product*.

---

## 1. What this is

A natural-language-to-SQL system built so that **the measurement apparatus around it is the centerpiece**, not the agent itself. Anyone can wire an LLM to a database; the senior signal is proving the system works, catching when it breaks, and operating it day to day.

The one-line pitch:

> A Guardrailed Agentic NL-to-SQL system, presented as a case study in rigorously evaluating and operating an LLM system — with the eval harness, observability, and prompt-CI/CD as the centerpiece; guardrails and self-correction as *measured* features underneath; open-sourced with a technical blog post; running against at least one cloud warehouse.

## 2. Why (target roles)

This single project is designed to cover the maximum common surface of four AI Engineer JDs (and to double as FDE-credible evidence):

- **Agent orchestration / function-calling** — every JD.
- **RAG + retrieval tuning** — every JD (here: RAG over *schema metadata*, not documents — a sharper framing).
- **LLMOps: eval, observability, CI/CD for prompts** — JKOPay, SWAG (the headline).
- **AI safety / guardrails: PII, prompt-injection, data boundaries** — JKOPay, enterprise-integration role.
- **Model selection (cost/latency/quality trade-offs)** — JKOPay explicitly.
- **Open-source + technical writing** — multiple JDs' nice-to-haves.
- **Cloud warehouse familiarity (BigQuery etc.)** — FDE / Wren AI.

Stack choices deliberately echo JKOPay's actual platform (LiteLLM Gateway, Langfuse, pgvector-style retrieval, GKE/containers) so the alignment is concrete and defensible — chosen on merit, not as keyword-stuffing.

## 3. Positioning / what makes it senior

The headline is **"rigorous evaluation and operation,"** not "I can generate SQL." Concretely that means:

- **Execution accuracy** via result-set comparison, never SQL string-match.
- **pass@1 vs pass@k** reported as twin metrics — the gap quantifies what self-correction is worth.
- **Naive-baseline vs retrieval** accuracy — quantifies what schema-RAG is worth.
- **Deterministic** guardrails (AST parsing, not regex; not LLM-judged) that are themselves *measured* against a red-team fixture.
- **Repeatability discipline** everywhere: frozen/seeded eval slices, version-controlled prompts, a committed results log where every reported number is traceable to its config and commit.

## 4. Architecture

### 4.1 Pipeline (the system under test)

An instrumented loop, modeled as a state machine with conditional edges:

```
question
   │
   ▼
[retrieve]  ── schema-RAG over table/column metadata + sample values
   │            (loop-aware: re-triggered on not-found errors)
   ▼
[generate]  ── LLM produces candidate SQL
   │
   ▼
[guard]     ── DETERMINISTIC, pre-execution gate (sqlglot AST):
   │            • read-only enforcement (no INSERT/UPDATE/DELETE/DROP)
   │            • dangerous-op blocking
   │            • cost/complexity heuristic (heuristic-FIRST; EXPLAIN only where engine supports it)
   │            • table-scope check (allowed-tables list, per-db)
   │            → on fail: reject OR feed back as correction signal
   ▼
[execute]   ── SQLAlchemy, multi-engine (SQLite for BIRD, Postgres for demo, BigQuery later)
   │
   ▼ (on error / suspicious result)
[correct]   ── feed error back → regenerate (execution-error feedback)
   │            and/or re-trigger retrieval on column/table-not-found
   │            capped retry budget
   ▼
RAW VERIFIED RESULT ──────────► scored by harness (UPSTREAM of redaction)
   │
   ▼
[redact]    ── column-aware PII masking (deterministic, schema-driven)
   ▼
PRESENTED RESULT ─────────────► shown to user / logged to traces (redacted only)
```

### 4.2 Two pipeline exits (critical)

- **Raw verified result** — what the harness scores against gold. Scoring happens here, **before** redaction.
- **Presented result** — post-redaction; what the user sees and what traces/logs record. Raw PII never reaches logs.

### 4.3 Terminal states (every run buckets into exactly one)

`success`, `wrong_answer` (ran clean, compared false), `retry_exhausted`, `execution_error_final`, `guardrail_rejected`, `retrieval_empty`. The classifier lives near the harness, not in the state dataclass. The failure taxonomy *is* the eval's analytical payload.

### 4.4 The harness (wraps the whole thing)

Treats the pipeline as `question → result`. Batch-capable, offline, repeatable (this is what later enables prompt-CI). For each test question: run pipeline, score via canonicalized result-set comparison, bucket terminal state, record cost/latency/attempts. Aggregates: overall accuracy, accuracy by difficulty/failure-type, **pass@1 and pass@k**, **retrieval recall** (vs the gold query's actual tables).

### 4.5 Observability

Each pipeline stage is a span; each run a trace (Langfuse). **Instrument-as-you-build**: thin logging seams added at each stage during Steps 1–7; Step 8 wires those seams to Langfuse and enforces redacted-logging. Captures cost/latency/tokens natively → feeds the pass@1-vs-pass@k cost analysis.

### 4.6 Prompt-CI/CD

Prompts are version-controlled templates. On change, a GitHub Action runs the harness against a **frozen, seeded, stratified** BIRD slice and posts pass@1/pass@k deltas. A delta means a real regression, not sampling noise.

## 5. Key design decisions (and their defenses)

| Decision | Choice | Why (interview one-liner) |
|---|---|---|
| Comparison | Result-set, canonicalized | "Two different queries can be equally correct; string-match is the rookie error." |
| Comparator correctness | Golden fixture of (gold, candidate, verdict) triples | "Here's how I *prove* my scorer is correct — otherwise 'BIRD-aligned' is just an assertion." |
| Guardrails | Deterministic AST (sqlglot), not regex/LLM | "Safety-critical checks must be deterministic and testable, not probabilistic." |
| Cost check | Heuristic-first; EXPLAIN as Postgres-only enhancement | "BIRD is SQLite — no cost-bearing EXPLAIN — so the heuristic is the primary path, not the fallback." |
| Self-correction eval | pass@1 AND pass@k | "Allowing retries means partly grading the corrector; two numbers tell the real story." |
| Retrieval failure | Measured (retrieval-recall), not pretended-fixed | "Silent wrong-schema retrieval can't be fixed at runtime — so I measure it instead." |
| DB scope | Single-db per run, db identity as input | "BIRD tags each question's db; cross-db *routing* is a different, harder problem I scoped out deliberately." |
| Framework | Hand-rolled first → LangGraph after logic proven | "I used a framework where it earned its place; my state machine *is* a graph with conditional edges." |
| Provider | LiteLLM (multi-provider) | "Makes the cross-provider cost/accuracy table trivial; also JKOPay's actual gateway." |
| Redaction vs scoring | Score upstream, log/present downstream | "Redaction must not corrupt scoring, and raw PII must never hit logs." |

## 6. Data

- **BIRD** — hard, realistic public benchmark = the *quantitative backbone*. Cited, not demoed. Provides large-N comparable accuracy and leaderboard anchoring. Honest "where I fail and why" beats a suspiciously-high Spider number.
- **Payments-platform schema** (Postgres) — hand-built *qualitative showcase*: users, merchants, transactions, payment_methods, refunds, disputes, ledger/balances. ~30–60 hand-authored questions with **verified** gold answers. Drives the demo, the guardrail exercise (natural PII + dangerous-op surface), and serves as the trusted ground for validating the harness before pointing it at BIRD.
- **BigQuery** (Phase 3, optional reach) — the cloud-warehouse checkbox.

## 7. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language / tooling | Python 3.11+, `uv` | Current-era tooling is a small but noticed signal. |
| Agent loop | Hand-rolled state machine → **LangGraph** (Step 7) | Plain Python is a legit permanent fallback if framework friction threatens timeline. |
| SQL parsing/validation | **sqlglot** | AST + cross-dialect transpilation. (`sqlparse` is tokenize-only — insufficient.) Keep from day one; it's stable. |
| DB access | SQLAlchemy | Engine-agnostic executor. |
| Databases | SQLite (BIRD), Postgres (demo), BigQuery (reach) | sqlglot transpiles across them. |
| LLM provider | **LiteLLM** (Step 7); direct single-provider before that | Multi-provider comparison artifact; JKOPay alignment. |
| Observability | **Langfuse** | Span/trace per stage; open-source; JD overlap. Log redacted only. |
| Eval harness | Hand-built, thin | The centerpiece — must be legible and owned, not framework-buried. |
| Prompt-CI | **GitHub Actions** | Runs frozen slice on prompt change, posts deltas. |
| Prompts | Jinja-style templates | Variable substitution for injected schema/few-shots; clean CI diffs. |
| Demo UI | Streamlit (deferred, isolated deps) | Must *reveal the wrapper* (guardrail decision, retry count, cost) — not hide a chatbot. |

## 8. Repo structure

```
nl2sql-eval/
  pyproject.toml            # uv-managed
  README.md                 # the portfolio front door (non-negotiable)
  RESULTS.md                # committed running results log (cross-cutting; see §10)
  PRD.md                    # this doc
  plans/                    # plan-step-1.md … plan-step-10.md
  src/nl2sql/
    pipeline/               # the system-under-test
      graph.py              # state machine (LangGraph after Step 7; hand-rolled before)
      state.py              # shared run state + terminal-state ENUM (enum only; classifier lives in harness)
      retrieve.py           # schema-RAG, loop-aware
      generate.py           # SQL generation
      guard.py              # deterministic AST guardrails (sqlglot), heuristic-first cost
      execute.py            # SQLAlchemy execution, multi-engine
      correct.py            # error / retrieval feedback loop
      redact.py             # column-aware PII masking (post-scoring)
    schema_index/           # retrievable schema-metadata store
    llm/                    # LiteLLM provider abstraction (direct single-provider pre-Step 7)
    obs/                    # Langfuse instrumentation helpers (thin seams from Step 1)
  eval/                     # CENTERPIECE — peer of src/, imports the pipeline
    harness.py              # batch runner; pass@1 + pass@k; terminal-state classifier
    compare.py              # canonicalization + result-set comparison (heavily tested)
    metrics.py              # accuracy, retrieval-recall, cost/latency aggregation
    datasets/
      bird/                 # benchmark backbone (loader/adapter); frozen slice ID list lives here
      payments/             # verified domain set + schema DDL
  fixtures/
    golden_compare/         # (gold, candidate, expected_verdict) triples — DELIVERABLE
    redteam_guard/          # injected dangerous queries — DELIVERABLE
  prompts/                  # version-controlled templates (CI diffs these)
  apps/demo/                # thin UI (built late; isolated dep group)
  tests/                    # esp. compare.py and guard.py — the deterministic cores
  .github/workflows/eval.yml # prompt-CI: run frozen slice on change, post deltas
```

Structural intentions: `eval/` is a **peer** of `src/` (evaluation is first-class). The pipeline is **import-shared** by harness and demo (no drift between what you demo and what you measure). `prompts/` externalized (CI can diff). `tests/` concentrates on `compare.py` and `guard.py` (the deterministic, correctness-critical cores).

## 9. Build sequence (summary)

The core inversion: **build the measurement apparatus (Steps 1–3) before the features**, so every feature arrives defined by the metric it produces.

| Step | Deliverable | Done when |
|---|---|---|
| 1 | Skeleton + payments db + thinnest hand-rolled loop | One payments question returns a correct result end-to-end |
| 2 | `compare.py` + golden fixture | Comparator passes its entire golden fixture |
| 3 | Minimal harness + first BIRD slice numbers (**Phase 1 DoD**) | First real pass@1 on a *small-schema* BIRD slice, from a validated comparator |
| 4 | Guardrails (schema-free: read-only, dangerous-op, cost heuristic) + red-team fixture | Guardrails unit-test green; "caught N% of red-team queries" |
| 5 | Self-correction (execution-error feedback only) + pass@k | Can state the pass@1→pass@k gap |
| 6 | Schema-RAG + loop-aware re-trigger + retrieval-recall + table-scope guardrail + large-schema slice | Retrieval recall reported; loop re-retrieves on not-found; retrieval-lift number recorded |
| 7 | Swap in LangGraph + LiteLLM; cross-provider table | Same-or-better numbers post-refactor; multi-provider results table |
| 8 | Wire observability seams to Langfuse; enforce redacted-logging | Any failing question diagnosable from its trace |
| 9 | Prompt-CI | A prompt edit triggers an automated eval run with reported deltas |
| 10 | Polish & reach | README + blog (non-negotiable) done; BigQuery (optional reach) |

See `plans/plan-step-N.md` for each step in detail.

## 10. Cross-cutting requirement — the running results log

From **Step 3 onward**, a step's *done-when is not met* until its number is appended to a committed `RESULTS.md` with the exact config that produced it: **model, slice ID, prompt version, date, the number, and the commit**. This is the harness's repeatability discipline applied to the *narrative*: every claim in the eventual blog is traceable to a committed run, not reconstructed from memory. Interview payoff: "every number in my writeup links to the commit and config that produced it." The blog then assembles from a trail of verified entries — it writes itself, and honestly.

The two sharpest findings to capture as they happen: the **pass@1→pass@k gap** (Step 5) and the **naive-baseline→retrieval lift** (Step 6).

## 11. Out of scope (deliberate, defensible)

- **Cross-database routing** — BIRD gives the target db per question; routing is a separate, harder problem with its own metric. Great "how would you extend this" answer; not built.
- **Open-ended generation eval** (summaries/chat) — no objective ground truth; would undercut the rigorous-eval thesis.
- **LLM-as-judge as primary scorer** — execution accuracy gives objective ground truth; judge avoided as the core metric.

## 12. Risks

- **Comparator subtle bugs** silently invalidate every number → mitigated by the golden fixture (Step 2).
- **Self-correction masks cost/latency** → mitigated by pass@1-vs-pass@k + cost tracking.
- **Naive-schema-dump tanks early BIRD accuracy** → mitigated by small-schema slice first; framed as deliberate baseline.
- **Framework/provider churn** → mitigated by hand-rolled-first, swap-in only after logic proven.
- **BigQuery integration risk** (auth/dialect/cost) → quarantined as optional reach; never blocks README/blog.
