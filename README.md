# nl2sql-eval

**A Guardrailed Agentic NL-to-SQL system — presented as a case study in rigorously evaluating and operating an LLM system.**

The natural-language-to-SQL agent is the *workload*; the eval harness, observability, and prompt-CI/CD wrapper around it is the *product*. Anyone can wire an LLM to a database — the goal here is to **prove the system works, catch when it breaks, and operate it day to day**. Guardrails and self-correction are not claimed features; they are *measured* features, scored against frozen benchmarks and red-team fixtures, with every reported number traceable to its config and commit.

> Open-sourced with a technical blog post, running against at least one cloud warehouse.

## Assumptions

The PRD (`docs/prd.md`) does not specify everything needed to run a project end-to-end. The following are inferred defaults; they will be replaced by real values as the implementation lands:

- **Tooling:** `uv` + `pyproject.toml` are mandated; exact command names (`uv run pytest`, etc.) are inferred.
- **Lint/format:** Assumed `ruff`. Confirm in `pyproject.toml`.
- **Python version:** Floor assumed at 3.11.
- **License:** Not specified in the PRD — placeholder below.
- **Environment variable names:** Inferred placeholder conventions, not PRD-specified.

## Features

- **Instrumented NL-to-SQL pipeline** modeled as a state machine with conditional edges: retrieve → generate → guard → execute → correct → redact.
- **Schema-RAG** over table/column metadata and sample values (retrieval over *schema*, not documents), loop-aware and re-triggered on not-found errors.
- **Deterministic guardrails** (sqlglot AST, not regex/LLM): read-only enforcement, dangerous-op blocking, cost/complexity heuristic, and per-db table-scope checks.
- **Self-correction loop** with a capped retry budget, feeding execution errors and retrieval misses back into regeneration.
- **Column-aware PII redaction** that runs *after* scoring, so raw PII never reaches logs or traces.
- **A first-class eval harness** reporting execution accuracy via canonicalized result-set comparison, `pass@1` vs `pass@k`, retrieval recall, and accuracy by difficulty/failure-type.
- **A proven comparator** validated against a golden fixture of `(gold, candidate, expected_verdict)` triples.
- **Measured guardrails** scored against a red-team fixture of injected dangerous queries.
- **Observability** with a Langfuse span per stage and trace per run (redacted logging only).
- **Prompt-CI/CD** via GitHub Actions: a prompt change runs the harness on a frozen, seeded, stratified BIRD slice and posts `pass@1`/`pass@k` deltas.
- **Multi-provider** model comparison through LiteLLM (cost/latency/quality trade-offs).
- **A committed running results log** (`RESULTS.md`) where every reported number links to the model, slice, prompt version, date, and commit that produced it.

## Prerequisites

- **Python 3.11+**
- **[uv](https://github.com/astral-sh/uv)** — package and project manager
- **SQLite** — for the BIRD benchmark (bundled with Python)
- **PostgreSQL** — for the payments demo database
- **An LLM provider API key** — every model call goes through LiteLLM (Step 7); the backend is chosen by the model identifier (`anthropic/…` for a direct key, `openrouter/…` to reach many models through one key) and the matching key is read from the environment.
- **A Langfuse account / keys** — for observability (Step 8 onward)
- **(Optional, Phase 3 reach)** Google Cloud project with BigQuery access
- **BIRD benchmark data** — downloaded separately (see `eval/datasets/bird/`)

## Installation

```bash
# 1. Clone the repository
git clone <repo-url> nl2sql-eval
cd nl2sql-eval

# 2. Install dependencies (uv reads pyproject.toml and creates the virtualenv)
uv sync

# 3. Provide configuration (see Configuration below)
cp .env.example .env     # then edit .env with your keys and DB URLs

# 4. (Optional) start a local Postgres for the payments demo, then load its schema
#    DDL and verified questions live under eval/datasets/payments/
docker compose up -d                                # local Postgres on :5432
uv run python -m eval.datasets.payments.load        # apply DDL + seed, then verify
uv run python -m eval.datasets.payments.verify_gold # check gold_sql reproduces gold_result

# 5. (Optional) download the BIRD benchmark data into eval/datasets/bird/

# 6. Verify the deterministic cores pass
uv run pytest tests/test_compare.py tests/test_guard.py
```

> Exact `.env` keys and dataset-loading commands depend on the implementation; follow the loaders under `eval/datasets/`.

## Usage

Run the eval harness against a dataset slice — this is the centerpiece. It runs the pipeline per question, scores against gold via result-set comparison, buckets the terminal state, and records cost/latency/attempts.

```bash
# Run the harness on a frozen BIRD slice
uv run python -m eval.harness --dataset bird --slice <frozen-slice-id>

# Run against the payments demo set
uv run python -m eval.harness --dataset payments
```

> Note: the harness CLI flags above (`--dataset`, `--slice`) show the intended interface; the batch runner lands from Step 3 onward.

Launch the demo UI — built to *reveal the wrapper* (guardrail decision, retry count, cost), not to hide a chatbot:

```bash
uv run streamlit run apps/demo/app.py
```

While the harness and demo are still being built, the thinnest pipeline loop
(Step 1) is runnable directly as a smoke check — it feeds one question through
`generate → execute → return` against the payments db (needs a live, seeded
Postgres and a provider key for the default model — `ANTHROPIC_API_KEY` for the
default `anthropic/claude-sonnet-4-6`):

```bash
uv run python -m nl2sql.pipeline.graph "How many users are based in the US?"
```

The Step-1 end-to-end proof goes one further: it runs a *verified seed question*
through the same loop, classifies the terminal state (`success` /
`execution_error_final`), and asserts the result reproduces the question's gold
answer (value-level match, column aliases ignored — the canonicalized comparator
lands at Step 2). Same prerequisites; exits non-zero on a mismatch:

```bash
uv run python -m eval.prove_step1            # defaults to pay-001
uv run python -m eval.prove_step1 pay-004    # any verified seed question id
```

**Every run buckets into exactly one terminal state:** `success`, `wrong_answer`, `retry_exhausted`, `execution_error_final`, `guardrail_rejected`, or `retrieval_empty`. The harness aggregates overall accuracy, accuracy by difficulty/failure-type, `pass@1`/`pass@k`, and retrieval recall.

## Configuration

Configuration is supplied via environment variables (e.g. an `.env` file). Names below are inferred placeholders — confirm against the implementation.

| Variable | Description | Required | Example |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Read by LiteLLM for `anthropic/…` models (the default `anthropic/claude-sonnet-4-6`) | Generate stage | `sk-ant-...` |
| `OPENROUTER_API_KEY` | Read by LiteLLM for `openrouter/…` models — one key, many backends | When using an `openrouter/…` model | `sk-or-...` |
| `PAYMENTS_DB_URL` | SQLAlchemy URL for the Postgres demo db | Demo only | `postgresql://payments:payments@localhost:5432/payments` |
| `BIRD_DATA_DIR` | Path to downloaded BIRD SQLite databases | BIRD runs | `./eval/datasets/bird/data` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key (observability) | Step 8+ | `pk-lf-...` |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | Step 8+ | `sk-lf-...` |
| `LANGFUSE_HOST` | Langfuse host URL | Step 8+ | `https://cloud.langfuse.com` |
| `RETRY_BUDGET` | Max self-correction attempts per question | No | `3` |
| `BIGQUERY_PROJECT` | GCP project for BigQuery (Phase 3 reach) | No | `my-gcp-project` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service-account JSON | No | `./gcp-key.json` |

The **model is chosen per run** by the provider-prefixed `model` argument to `run_pipeline` (default `anthropic/claude-sonnet-4-6`); LiteLLM routes to the matching backend and reads the corresponding key above. No separate provider/key env var is needed — the identifier *is* the selector.

## Project Structure

```
nl2sql-eval/
├── pyproject.toml            # uv-managed project + dependencies
├── docker-compose.yml        # local Postgres for the payments demo db
├── .env.example              # template for .env (PAYMENTS_DB_URL, keys, …)
├── README.md                 # this file — the portfolio front door
├── RESULTS.md                # committed running results log (every number → config + commit)
├── docs/
│   ├── prd.md                # product requirements document
│   └── plans/                # per-step detail, one folder per step
│       ├── step-1/           #   plan-step-1.md + its broken-down issue-*.md slices
│       ├── step-2/ … step-10/#   plan-step-N.md per step
│       └── …
├── src/nl2sql/
│   ├── pipeline/             # the system-under-test (import-shared by harness + demo)
│   │   ├── graph.py          #   state machine (LangGraph after Step 7; hand-rolled before)
│   │   ├── state.py          #   shared run state + terminal-state ENUM (enum only)
│   │   ├── retrieve.py       #   schema-RAG, loop-aware
│   │   ├── generate.py       #   LLM SQL generation
│   │   ├── guard.py          #   deterministic sqlglot AST guardrails, heuristic-first cost
│   │   ├── execute.py        #   SQLAlchemy execution, multi-engine
│   │   ├── correct.py        #   error / retrieval feedback loop (capped retries)
│   │   └── redact.py         #   column-aware PII masking (post-scoring)
│   ├── schema_index/         # retrievable schema-metadata store
│   ├── llm/                  # LiteLLM provider boundary (the LLMClient seam)
│   └── obs/                  # Langfuse instrumentation helpers (thin seams)
├── eval/                     # CENTERPIECE — peer of src/, imports the pipeline
│   ├── harness.py            #   batch runner; pass@1 + pass@k; terminal-state classifier
│   ├── prove_step1.py        #   Step-1 end-to-end proof: one seed question → result vs gold
│   ├── compare.py            #   canonicalization + result-set comparison (heavily tested)
│   ├── metrics.py            #   pass@1/pass@k twin report, cost/latency aggregation
│   ├── cost.py               #   token→USD price table (dated); pass@k cost accounting
│   └── datasets/
│       ├── bird/             #   benchmark backbone; frozen slice ID list lives here
│       └── payments/         #   schema.sql + seed.sql + load.py; questions.json + questions.py + verify_gold.py
├── fixtures/
│   ├── golden_compare/       # (gold, candidate, expected_verdict) triples — DELIVERABLE
│   └── redteam_guard/        # injected dangerous queries — DELIVERABLE
├── prompts/                  # version-controlled Jinja-style templates (CI diffs these)
├── apps/demo/                # thin Streamlit UI (built late; isolated dep group)
├── tests/                    # esp. compare.py and guard.py — the deterministic cores
└── .github/workflows/
    └── eval.yml              # prompt-CI: run frozen slice on change, post deltas
```

## Testing

Tests concentrate on the **deterministic, correctness-critical cores**: the comparator (`eval/compare.py`) and the guardrails (`src/nl2sql/pipeline/guard.py`). A comparator bug silently invalidates every reported number, so the comparator must pass its **entire** golden fixture, and guardrails are measured against the red-team fixture.

```bash
# Full suite
uv run pytest

# The deterministic cores
uv run pytest tests/test_compare.py tests/test_guard.py
```

- **Comparator:** validated against `fixtures/golden_compare/` — `(gold, candidate, expected_verdict)` triples. Add a fixture case for every new comparison edge case. The committed rule set and its **per-rule audit against the official BIRD evaluator** (including the deliberate divergences and the opt-in `BIRD_RULES` for leaderboard parity) live in [`docs/eval/comparator-rule-set.md`](docs/eval/comparator-rule-set.md).
- **Guardrails:** unit-test green plus a reported catch rate against `fixtures/redteam_guard/`. Add a fixture case for every new dangerous-query pattern.
- **Payments gold set** (`eval/datasets/payments/questions.json`) carries two distinct, independent flags:
  - `machine_verified` — the agent's claim that `gold_sql` reproduces the stored `gold_result` against the seed. Reproduce it (needs a live, seeded db):
    ```bash
    docker compose up -d
    uv run python -m eval.datasets.payments.load
    uv run python -m eval.datasets.payments.verify_gold   # exits non-zero on any mismatch
    ```
    `tests/test_payments_questions.py` is the CI-safe (no-db) structural guard for the same file.
  - `human_reviewed` — a human's separate sign-off that each question's wording matches intent. The agent never self-ticks it; flip it to `true` only after eyeballing the questions against the seeded rows.

## Configuration & Data Sources

- **BIRD** — hard, realistic public benchmark; the quantitative backbone. Provides large-N comparable accuracy and leaderboard anchoring.
- **Payments-platform schema (Postgres)** — hand-built qualitative showcase (users, merchants, transactions, payment_methods, refunds, disputes, ledger/balances) with ~30–60 verified gold answers. Drives the demo and the guardrail/PII exercise.
- **BigQuery** — optional Phase 3 reach; the cloud-warehouse checkbox. Quarantined so it never blocks the README/blog.

## Contributing

> Inferred conventions — adjust to project norms once established.

- **Branch strategy:** feature branches off `main`; open a pull request for review. Do not commit directly to `main`.
- **Prompts:** edit templates in `prompts/` (never inline prompt strings). Prompt-CI diffs this directory and posts `pass@1`/`pass@k` deltas — a delta means a real regression, not sampling noise.
- **Results discipline:** from Step 3 onward, any eval number you report must be appended to `RESULTS.md` with **model, slice ID, prompt version, date, the number, and the commit**.
- **Code style:** Python 3.11+, formatted/linted with `ruff` (assumed). Run `uv run ruff check .` and `uv run ruff format .` before opening a PR.
- **Tests:** `uv run pytest` must pass; extend the golden and red-team fixtures when touching the comparator or guardrails.
- **Out of scope** (do not submit): cross-database routing, open-ended generation eval, and LLM-as-judge as the primary scorer.

## License

License not specified in the PRD. **TBD** — add a `LICENSE` file (e.g. MIT or Apache-2.0) before open-sourcing.
