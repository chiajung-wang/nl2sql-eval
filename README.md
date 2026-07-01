# nl2sql-eval

**A Guardrailed Agentic NL-to-SQL system — presented as a case study in rigorously evaluating and operating an LLM system.**

The natural-language-to-SQL agent is the *workload*; the eval harness, observability, and prompt-CI/CD wrapper around it is the *product*. Anyone can wire an LLM to a database — the goal here is to **prove the system works, catch when it breaks, and operate it day to day**. Guardrails and self-correction are not claimed features; they are *measured* features, scored against frozen benchmarks and red-team fixtures, with **every reported number traceable to its config and commit** in [`RESULTS.md`](RESULTS.md).

## Headline findings

Each row links to its committed entry in [`RESULTS.md`](RESULTS.md), where the exact model, slice, prompt version, date, and commit are recorded. The findings are deliberately *honest* — several are null or negative results, which is the point: the apparatus tells you the truth, not the headline you hoped for.

Each "Source" cell links to the committed [`RESULTS.md`](RESULTS.md) log and names the exact commit that produced the number.

| Finding | Number | What it means | Source (commit) |
|---|---|---|---|
| **First real BIRD number** (pass@1) | 0.420 (21/50) | The naive schema-dump baseline on a frozen, stratified 50-question slice | [Step 3](RESULTS.md#log) · `5d9d8ae` |
| **Guardrail catch rate** (red-team) | 1.000 (29/29) | Every dangerous query in the red-team fixture blocked pre-execution; 43/43 verdicts correct | [Step 4](RESULTS.md#log) · `e56fbcd` |
| **What self-correction is worth** (pass@1→pass@k) | strong model **+0.000**; weak model **+0.050** | The loop can only recover *execution errors*. A strong model makes ~none (its failures are semantic) so the gap is **0** even on 14-table schemas; a weaker generator produces them and the loop recovers some. The value tracks **generator weakness**, not budget — the twin reports the lift with its retry price | [Step 5](RESULTS.md#log) · `7ae5bb5` + [follow-up](RESULTS.md#log) · `fc99e7c` |
| **What retrieval is worth** (naive→schema-RAG lift) | 0.700 → 0.575, lift **−0.125**, recall 0.942 | Where the whole schema *fits* the context, RAG can only lose information by dropping a needed table; recall diagnoses the loss directly | [Step 6](RESULTS.md#log) · `ff342d7` |
| **Cross-provider** (accuracy × cost × latency) | best pass@1 **0.540** (`gemini-3-flash`) | One import-shared pipeline, many providers via LiteLLM; cheapest model ~70× less than priciest | [Step 7](RESULTS.md#log) · `26328de` |
| **Framework-swap parity** (pass@1) | 0.420 → 0.420 | LangGraph + LiteLLM refactor was behavior-preserving — the harness proves the swap changed *exactly nothing* | [Step 7](RESULTS.md#log) · `2040ef9` |
| **Prompt-CI catches a regression** (pass@1/pass@k) | 0.417 → **0.000**, Δ **−0.417** | A reasonable-looking prompt edit, caught before merge by the CI delta | [Step 9](RESULTS.md#log) · `157fe6b` |

## Architecture

The pipeline is an **instrumented state machine** wrapped by a harness that treats it as `question → result`. The same compiled graph is **import-shared** by the eval harness and the demo — never forked — so there is no drift between what is measured and what is shown.

```mermaid
flowchart LR
  Q([NL question]) --> R[retrieve<br/>schema-RAG, loop-aware]
  R --> G[generate<br/>LLM SQL]
  G --> GU{guard<br/>sqlglot AST}
  GU -- rejected --> X1((guardrail_rejected))
  GU -- allowed --> E[execute<br/>SQLAlchemy]
  E -- error --> C[correct<br/>capped retry]
  C --> G
  E -- clean --> RAW[/raw verified result/]
  RAW --> SCORE[[harness: score vs gold<br/>canonicalized result-set compare]]
  RAW --> RED[redact<br/>column-aware PII mask]
  RED --> PRES[/presented result/]
  PRES --> LOG[(logs · traces · UI)]
  classDef exit fill:#fde68a,stroke:#d97706,color:#7c2d12;
  class RAW,PRES exit;
```

**The two pipeline exits are the crux of the design:**

- **Raw verified result** — scored by the harness against gold, **upstream of redaction**. Two different queries can be equally correct, so scoring is canonicalized result-set comparison, never SQL string-match.
- **Presented result** — post-redaction; the *only* thing shown to users or written to traces/logs. Raw PII never reaches a log line, a span, or the screen.

**Every run buckets into exactly one terminal state:** `success`, `wrong_answer`, `retry_exhausted`, `execution_error_final`, `guardrail_rejected`, or `retrieval_empty` — the classifier lives in the harness, the enum in `state.py`.

## Features

- **Instrumented NL-to-SQL pipeline** modeled as a state machine with conditional edges: retrieve → generate → guard → soundness → execute → correct → redact (the `soundness` checks are correction signals, not a hard gate).
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
- **A Langfuse account / keys** — for observability (optional; offline it is pure structured logging)
- **BIRD benchmark data** — downloaded separately (see `eval/datasets/bird/`)

> **BigQuery is a documented future reach, not built.** The cloud-warehouse executor (sqlglot transpilation to the BigQuery dialect) was scoped as optional reach and deliberately deferred — it carries real integration risk (auth, dialect quirks, cost) that must never block the legibility deliverables. The executor is already multi-engine and the guard already recognizes the `bigquery` dialect, so the path is open; the connection itself is left for a follow-up. See *Planning*.

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

# 5. (Optional) download the BIRD benchmark data into eval/datasets/bird/data
#    (gitignored; point BIRD_DATA_DIR at it — see Configuration)

# 6. Verify the deterministic cores pass
uv run pytest tests/test_compare.py tests/test_guard.py
```

## Usage

The eval harness is the centerpiece: each runner drives the import-shared pipeline per question over a **frozen** slice, scores against gold via canonicalized result-set comparison, buckets the terminal state, records cost/latency/attempts, and appends the number to `RESULTS.md`. Each runner is a thin entrypoint over the shared `eval/harness.py` batch runner; all accept `--dry-run` to print without writing. A provider key is required for the live model call (see Configuration).

```bash
# Step 3 — pass@1 baseline on the frozen BIRD slice (naive schema dump)
uv run python -m eval.eval_bird

# Step 5 — the twin metric: pass@1 vs pass@k and the cost the gap buys
uv run python -m eval.eval_bird_twin

# Step 5 follow-up — where self-correction actually fires: the twin on the
# large-schema slice, with a selectable generator (MODEL env var). A strong model
# makes ~0 execution errors (gap 0); a weaker one gives the loop something to fix.
uv run python -m eval.eval_bird_selfcorrect
MODEL=openrouter/moonshotai/kimi-k2.7-code uv run python -m eval.eval_bird_selfcorrect

# Step 6 — naive-dump vs schema-RAG retrieval lift (+ retrieval recall)
uv run python -m eval.eval_bird_rag

# Step 4 — guardrail catch rate against the red-team fixture (deterministic, no model)
uv run python -m eval.redteam

# Step 7 — cross-provider table: accuracy × cost × latency per model.
# Models come from CROSS_PROVIDER_MODELS (see Configuration).
uv run python -m eval.eval_cross_provider

# The payments demo set (Postgres) instead of BIRD
uv run python -m eval.eval_payments
```

Each step also ships a self-contained **proof** that runs offline (no API key) where possible — e.g. `eval.prove_step1` (one seed question → result vs gold), `eval.prove_step8` (renders an example trace), `eval.prove_step9` (replays the prompt-CI regression delta).

**Prompt-CI/CD (Step 9).** A prompt change automatically tells you whether you improved or regressed. The GitHub Action [`.github/workflows/eval.yml`](.github/workflows/eval.yml) triggers on any change under `prompts/` (or `src/nl2sql/prompts.py`, where the active version is pinned), runs the harness on the **frozen, seeded, stratified** prompt-CI slice ([`slice_ci.json`](eval/datasets/bird/slice_ci.json), generated by [`slice_ci.py`](eval/datasets/bird/slice_ci.py)) with both the base and PR prompts, and posts the **pass@1/pass@k deltas** to the job summary and a sticky PR comment.

```bash
# Live: run the frozen prompt-CI slice and write a report (needs a provider key)
uv run python -m eval.prompt_ci --report report.json

# Offline: render the base→PR pass@1/pass@k delta as Markdown (no model)
uv run python -m eval.prompt_ci --compare base.json head.json
```

> **Cost guard:** the prompt-CI slice is deliberately small (12 questions). Each push runs it twice (base + PR), each a pass@k run, so per-push cost scales with `size × k × 2` — a fixed small subset, not full BIRD per push. The slice is frozen, seeded, and stratified by BIRD difficulty so a delta is a real regression, not sampling variance. The live run is gated on `ANTHROPIC_API_KEY` + a `BIRD_DEV_URL` repo variable (defer-API-key); without them the workflow reports a skipped run instead of failing the PR.

**Demo UI.** A thin Streamlit app (`apps/demo/`) *reveals the wrapper* — the guardrail decision, retry count, cost, and terminal state for each question — rather than hiding a chatbot. It imports the **same shared pipeline** the harness measures (and the harness's own terminal-state classifier), so the demo can't drift from the numbers, and it only ever shows the *presented (redacted)* result. Its dependencies are isolated in their own group:

```bash
uv sync --group demo
uv run streamlit run apps/demo/app.py
```

Pick a dataset in the sidebar — `payments` (the Postgres demo with PII columns, the redaction showcase) or `bird/<db_id>` (a BIRD SQLite db) — enter a question, and the run surfaces the machinery, not a chat bubble.

The thinnest pipeline loop is runnable directly as a smoke check — one question through `generate → guard → execute → return` against the payments db (needs a live, seeded Postgres and a provider key for the default `anthropic/claude-sonnet-4-6`):

```bash
uv run python -m nl2sql.pipeline.graph "How many users are based in the US?"
```

## Configuration

Configuration is supplied via environment variables (e.g. an `.env` file).

| Variable | Description | Required | Example |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Read by LiteLLM for `anthropic/…` models (the default `anthropic/claude-sonnet-4-6`) | Generate stage | `sk-ant-...` |
| `OPENROUTER_API_KEY` | Read by LiteLLM for `openrouter/…` models — one key, many backends | When using an `openrouter/…` model | `sk-or-...` |
| `PAYMENTS_DB_URL` | SQLAlchemy URL for the Postgres demo db | Demo only | `postgresql://payments:payments@localhost:5432/payments` |
| `BIRD_DATA_DIR` | Path to downloaded BIRD SQLite databases | BIRD runs | `./eval/datasets/bird/data` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key (observability) | Step 8+ | `pk-lf-...` |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | Step 8+ | `sk-lf-...` |
| `LANGFUSE_HOST` | Langfuse host URL — set to your region (EU `cloud.langfuse.com`, US `us.cloud.langfuse.com`, JP `jp.cloud.langfuse.com`, or self-hosted). `LANGFUSE_BASE_URL` is honored as a fallback. | Step 8+ | `https://cloud.langfuse.com` |
| `RETRY_BUDGET` | Max self-correction attempts per question | No | `3` |
| `RUN_CONFIG` | Named run config bundling model + token budget (`accuracy` or `list-priced`); unset → `list-priced` default. An explicit `MODEL`/`MAX_TOKENS` overrides the bundle. | No | `accuracy` |
| `MODEL` | Override the generator model for eval runs (recorded in `RESULTS.md`); unset → the active `RUN_CONFIG`'s model | No | `openrouter/google/gemini-3.5-flash` |
| `MAX_TOKENS` | Output-token budget per generate call; unset → 4096 (ample for reasoning models, a no-op ceiling otherwise) | No | `8192` |
| `SLICE` | Eval slice for `diagnose_bird` / `eval_bird_schema`: unset → the Step-3 dev slice (50); `holdout` → the held-out test slice (100, touch once); `dev-wide` → the wide dev slice (250, tighter sampling noise, #133) | No | `dev-wide` |
| `METADATA_SOURCE` | Field-description source for the schema index (#140): unset → `supplied` (current behaviour); `profiling` → data-derived only; `fused` → supplied + profiling (the paper's best). Reads the version-controlled `profiles/<db>.json` cache; a db without one degrades to `supplied`. | No | `fused` |
| `LITERAL_STEER` | Enable literal→field steering (#141): a post-generation check that flags a string literal constrained against a column whose sampled values don't contain it (while another column does) and feeds a steering correction. Off by default (unset/`0`) → byte-identical run; `1`/`true` builds the value index and turns the check on. | No | `1` |
| `CROSS_PROVIDER_MODELS` | Comma-separated model ids for the Step-7 cross-provider table; unset → the default single model | Step 7 cross-provider run | `openrouter/anthropic/claude-sonnet-4,openrouter/openai/gpt-4o-mini` |

The **model is chosen per run** by the provider-prefixed `model` argument to `run_pipeline` (default `anthropic/claude-sonnet-4-6`); LiteLLM routes to the matching backend and reads the corresponding key above. No separate provider/key env var is needed — the identifier *is* the selector.

> **Named run configs (`RUN_CONFIG`, Step 11 #132)** — pick an *axis* by name instead of hand-assembling `MODEL` + `MAX_TOKENS`:
>
> - **`accuracy`** — `openrouter/google/gemini-3.5-flash` + `MAX_TOKENS=4096` (needs `OPENROUTER_API_KEY`). The top model on the frozen slice at **pass@1 0.520 / 0.580 BIRD** ([RESULTS.md](RESULTS.md#log) — Step 11 #124), above `gemini-3-flash-preview` (0.500/0.560) and the sonnet baseline (0.420/0.460). It's a *reasoning* model: it spends ~1000–1150 tokens thinking before emitting SQL, so it relies on the bundled `MAX_TOKENS=4096` — at the old 1024 cap it truncated mid-thought and looked broken. ~$0.009/query.
> - **`list-priced` (default)** — the pinned `anthropic/claude-sonnet-4-6`, a *direct, list-priced* model so `eval.cost` prices it dollar-for-dollar. Unset `RUN_CONFIG` resolves here — a clean checkout reproduces the committed baseline.
>
> **Precedence:** an explicit `MODEL` / `MAX_TOKENS` still wins over the bundle (so a pinned dev `MODEL` shadows `RUN_CONFIG` — clear it to let `accuracy` take effect). The default stays sonnet deliberately — repinning to the OpenRouter gemini globally would make the project's default depend on a third-party aggregator and forfeit clean cost accounting (#117). A separate **cheap dev workhorse**, `openrouter/google/gemini-3.1-flash-lite` (matches the sonnet baseline **0.420 / 0.460** at a fraction of the cost, clean non-reasoning output), stays a per-knob `MODEL` override for fast local iteration.

**Reproduce the trace.** Tracing activates only when both Langfuse keys are set (offline it is pure structured logging — no keys, no network). With keys in `.env`, confirm export end to end before a full run:

```bash
uv run python -m eval.langfuse_smoke   # sends one trace, prints its URL
```

Then any `eval.eval_*` run (or the demo) produces one trace per question — a `pipeline` root (the NL question in, the redacted result-shape out) with a child span per stage and token/cost on the `generate` generation — filterable by the `db:` / `model:` tags. Each batch is also grouped into one **Langfuse Session** (`<mode>:<model>:<prompt>:<UTC date>`, e.g. `bird-naive:anthropic/claude-sonnet-4-6:v3:2026-06-18`), so a whole eval run is one comparable unit in the Sessions view — A/B modes (naive vs RAG, cross-provider) land in sibling sessions. The same trace is also captured offline for the blog via `uv run python -m eval.prove_step8`.

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
│   ├── blogs/                # the step-by-step technical narrative (step-1 … step-10)
│   └── plans/                # per-step detail, one folder per step
│       ├── step-1/           #   plan-step-1.md + its broken-down issue-*.md slices
│       ├── step-2/ … step-10/#   plan-step-N.md + per-issue summary HTML
│       └── …
├── src/nl2sql/
│   ├── pipeline/             # the system-under-test (import-shared by harness + demo)
│   │   ├── graph.py          #   state machine (LangGraph after Step 7; hand-rolled before)
│   │   ├── state.py          #   shared run state + terminal-state ENUM (enum only)
│   │   ├── retrieve.py       #   schema-RAG, loop-aware
│   │   ├── link.py           #   task-alignment schema linking (harvest tables from generated SQL, #138)
│   │   ├── generate.py       #   LLM SQL generation
│   │   ├── guard.py          #   deterministic sqlglot AST guardrails, heuristic-first cost
│   │   ├── soundness.py      #   deterministic bad-construction checks → correction signal (#139)
│   │   ├── literal_check.py  #   literal→field steering (right value, wrong column) → correction (#141)
│   │   ├── execute.py        #   SQLAlchemy execution, multi-engine
│   │   ├── correct.py        #   error / retrieval / soundness / literal feedback loop (capped retries)
│   │   └── redact.py         #   column-aware PII masking (post-scoring)
│   ├── schema_index/         # retrievable schema-metadata store
│   ├── value_index.py        # sampled value→column index for literal→field steering (#141)
│   ├── profiling/            # data profiler + mechanical English + offline LLM summary cache (#140)
│   ├── llm/                  # LiteLLM provider boundary (the LLMClient seam)
│   └── obs/                  # Langfuse instrumentation helpers (thin seams)
├── eval/                     # CENTERPIECE — peer of src/, imports the pipeline
│   ├── harness.py            #   batch runner; pass@1 + pass@k; terminal-state classifier
│   ├── prove_step1.py        #   Step-1 end-to-end proof: one seed question → result vs gold
│   ├── compare.py            #   canonicalization + result-set comparison (heavily tested)
│   ├── metrics.py            #   pass@1/pass@k twin report, cost/latency aggregation
│   ├── voting.py             #   result-set majority voting: the comparator as a candidate selector (#142)
│   ├── candidate_diversity.py #  seeded schema-field-order randomization for candidate diversity (#142)
│   ├── prompt_ci.py          #   prompt-CI: run frozen slice, render pass@1/pass@k delta
│   ├── cost.py               #   token→USD price table (dated); pass@k cost accounting
│   └── datasets/
│       ├── bird/             #   benchmark backbone; frozen slice ID lists (incl. slice_ci.json)
│       └── payments/         #   schema.sql + seed.sql + load.py; questions.json + questions.py + verify_gold.py
├── fixtures/
│   ├── golden_compare/       # (gold, candidate, expected_verdict) triples — DELIVERABLE
│   ├── redteam_guard/        # injected dangerous queries — DELIVERABLE
│   └── soundness/            # bad-construction (soundness) checks: catch + false-positive rate — DELIVERABLE
├── profiles/                 # version-controlled field-description cache (per db) — #140
├── prompts/                  # version-controlled Jinja-style templates (CI diffs these)
├── apps/demo/                # thin Streamlit UI revealing the wrapper (isolated dep group)
│   ├── runner.py             #   testable core: run_demo → DemoView (no Streamlit)
│   └── app.py                #   thin Streamlit shell over runner.py
├── tests/                    # esp. compare.py and guard.py — the deterministic cores
└── .github/workflows/
    └── eval.yml              # prompt-CI: run frozen slice on change, post deltas
```

## Planning

The project was built **measurement-first** (the eval before the feature) across ten steps, and the planning trail is committed so every decision and number is traceable:

- [`docs/prd.md`](docs/prd.md) — the product requirements document the whole build derives from.
- [`docs/plans/step-N/`](docs/plans/) — per-step plan plus its broken-down, independently-grabbable issues, each with a self-contained HTML summary of what shipped.
- [`RESULTS.md`](RESULTS.md) — the running results log; every reported number links to its model, slice, prompt version, date, and commit.
- [`docs/blogs/`](docs/blogs/) — the step-by-step narrative, capped by the [capstone](docs/blogs/the-wrapper-is-the-product.md).

**Status:** Steps 1–10 complete. The one deliberately deferred item is the optional BigQuery cloud-warehouse executor (the guard already recognizes the `bigquery` dialect; transpiling verified SQL via sqlglot is the remaining step).

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
- **Soundness checks (#139):** the deterministic bad-construction checks (`src/nl2sql/pipeline/soundness.py`) are measured against `fixtures/soundness/` — a reported **catch rate** and **false-positive rate** over positives + near-miss negatives. Unlike the guard these are *correction signals*, not hard rejects. Add a fixture case for every new soundness pattern.
- **Profiling (#140):** the deterministic profiler + mechanical English renderer + cache round-trip + metadata-source selector are unit-tested offline (`tests/test_profiling.py`) on an in-memory fixture db and an injected fake LLM client — no key needed. The LLM-summarized descriptions are **prompt content only**; they are never read by the guard or comparator, so scoring stays deterministic.
- **Literal→field steering (#141):** the sampled value index + sqlglot-AST literal check + steering + graph wiring are unit-tested offline (`tests/test_literal_field.py`) on an in-memory fixture db — the check recovers the paper's `CountyName`→`District` flip and stays silent on on-column / unknown literals (no false steer). The *matching* is deterministic (index lookup); only the rephrase is an LLM call, riding the `correct.py` loop.
- **Majority voting (#142):** the vote selector (`eval/voting.py`) **reuses `eval/compare.py`'s result-set equivalence** to pick among candidates — no new equivalence logic, no string-match, no LLM judge. Unit-tested offline (`tests/test_voting.py`) on recorded result-sets: unanimous / majority / no-majority with a deterministic earliest-index tiebreak, errored-candidate exclusion, and the seeded schema-field-order diversity lever. Voting *selects*; the harness still scores the selected raw result against gold, upstream of redaction.
- **Payments gold set** (`eval/datasets/payments/questions.json`) carries two distinct, independent flags:
  - `machine_verified` — the agent's claim that `gold_sql` reproduces the stored `gold_result` against the seed. Reproduce it (needs a live, seeded db):
    ```bash
    docker compose up -d
    uv run python -m eval.datasets.payments.load
    uv run python -m eval.datasets.payments.verify_gold   # exits non-zero on any mismatch
    ```
    `tests/test_payments_questions.py` is the CI-safe (no-db) structural guard for the same file.
  - `human_reviewed` — a human's separate sign-off that each question's wording matches intent. The agent never self-ticks it; flip it to `true` only after eyeballing the questions against the seeded rows.

## Data Sources

- **BIRD** — hard, realistic public benchmark; the quantitative backbone. Provides large-N comparable accuracy and leaderboard anchoring.
- **Payments-platform schema (Postgres)** — hand-built qualitative showcase (users, merchants, transactions, payment_methods, refunds, disputes, ledger/balances) with ~30–60 verified gold answers. Drives the demo and the guardrail/PII exercise.

## Contributing

- **Branch strategy:** feature branches off `main`; open a pull request for review. Do not commit directly to `main`.
- **Prompts:** edit templates in `prompts/` (never inline prompt strings). Prompt-CI diffs this directory and posts `pass@1`/`pass@k` deltas — a delta means a real regression, not sampling noise.
- **Results discipline:** any eval number you report must be appended to `RESULTS.md` with **model, slice ID, prompt version, date, the number, and the commit**.
- **Code style:** Python 3.11+, formatted/linted with `ruff`. Run `uv run ruff check .` and `uv run ruff format .` before opening a PR.
- **Tests:** `uv run pytest` must pass; extend the golden and red-team fixtures when touching the comparator or guardrails.
- **Out of scope** (do not submit): cross-database routing, open-ended generation eval, and LLM-as-judge as the primary scorer.

## License

No `LICENSE` file is committed yet. Add one (e.g. MIT or Apache-2.0) before open-sourcing — the choice is left to the repository owner.
