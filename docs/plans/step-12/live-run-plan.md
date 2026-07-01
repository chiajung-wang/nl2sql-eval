# Step 12 — Live-Run Plan (the deferred A/Bs)

Step 12 shipped five levers as **deterministic machinery + offline proofs**; every
accuracy number was deferred, recorded as a *pending* row in
[`RESULTS.md`](../../../RESULTS.md), gated on an authorized API key + spend. This is
the runbook to turn those pending rows into measured numbers. It is honest about what
is **runnable today** via an env axis versus what needs a small **day-0 wiring** first
(each piece is offline-testable and should be built + unit-tested *before* any spend).

> **The discipline still holds.** Every number produced here gets a `RESULTS.md` row
> (model, slice ID, prompt version, date, number, commit) that *replaces* its pending
> row. The held-out slice is spent **once** per lever, only after a dev lift. An honest
> null (a strong generator where the lever is a no-op) is a legitimate, expected result
> — several of these likely are, per Steps 5 and 11.

---

## 0. Prerequisites (before spending a cent)

1. **API key + budget.** OpenRouter key (`OPENROUTER_API_KEY`) for the `accuracy`
   config (`gemini-3.5-flash`) and the weak generator (`kimi-k2.7-code`); optionally an
   Anthropic key for a true-sonnet anchor. Confirm a spend ceiling.
2. **BIRD data present.** The live path needs the gitignored
   `eval/datasets/bird/data/dev.json` + the per-db SQLite files (see `README.md` →
   *Data Sources*). Absence of these is why `test_guard.py::test_cost_budget_clears_every_bird_slice_gold_query`
   is the one red test in CI — it is a data-availability gap, not a code bug.
3. **Reproduce the baseline first.** Before any lever, confirm the committed anchor
   reproduces on this machine so a lever's delta is trustworthy:
   ```bash
   RUN_CONFIG=list-priced uv run python -m eval.diagnose_bird     # expect pass@1 ≈ 0.420 (sonnet)
   RUN_CONFIG=accuracy    uv run python -m eval.diagnose_bird     # expect ≈ 0.520 / 0.580 (gemini-3.5-flash)
   ```

---

## 1. Day-0 wiring (small, offline-testable — build & `pytest`-green before spending)

Two levers are already wired to an env axis; three need a few lines each. Do the wiring,
unit-test it offline with the fake client (no key), land it, *then* spend.

| Lever | State | Wiring needed (where) |
|---|---|---|
| **#140** profiling metadata | ✅ wired | `METADATA_SOURCE` axis in `eval/eval_bird_rag.py:_index`. Only needs the artifacts (step 2A). |
| **#141** literal→field steering | ✅ wired | `LITERAL_STEER` axis in `eval/eval_bird_rag.py:_value_index`. Runnable as-is. |
| **#138** task-alignment linking | ⚠ param only | Add a `LINK_STRATEGY` env in `eval/eval_bird_rag.py` (mirror `LITERAL_STEER`) that passes `link_strategy="task_alignment"` to the RAG `run_pipeline`. `run_pipeline`/graph already accept it. |
| **#139** soundness A/B toggle | ⚠ always-on | Add a `SOUNDNESS` env (default on) + a `run_pipeline` flag that skips the `soundness`/`literal_check` stages when off, so "± the checks" is a real toggle. (At pass@1 the stage is inert — the A/B is meaningful only at pass@k.) |
| **#142** majority-voting twin | ⚠ selector only | Add `eval/eval_bird_vote.py`: per case run `voting.run_voted(run_one, k)` where `run_one(i)` runs the pipeline against `candidate_diversity.shuffle_field_order(index, seed=i)`; score the **selected raw result**. For the *seed* diversity lever, thread a `seed` through `run_pipeline → generate → LLMClient.complete` (the field-order lever needs no client change). |

All five wirings keep the offline test suites green (extend them with the new env
branch / runner using the existing fake client).

---

## 2. The five A/Bs (arms · command · record)

Shared knobs (see `README.md` → *Configuration*): `RUN_CONFIG` (`accuracy` = the strong
generator; unset/`list-priced` = sonnet baseline), `MODEL`/`MAX_TOKENS` (override the
bundle), `SLICE` (unset = dev 50, `dev-wide` = 250 with tighter noise, `holdout` = 100,
touch once). Run each lever on the **strong (`accuracy`) and a weak generator** — the
strong/weak contrast is where every lever in this series showed its true shape.

### 2A. #140 — profiling-derived metadata (precompute first)

```bash
# One-time precompute per db (the only step that calls a model for metadata):
uv run python -m nl2sql.profiling.summarize --db-url <sqlite-url> --db-id <db> --model <model>
#   → writes the version-controlled profiles/<db>.json ; commit it.

# A/B the three sources on the same generator (repeat for strong + weak):
for src in supplied profiling fused; do
  RUN_CONFIG=accuracy METADATA_SOURCE=$src uv run python -m eval.diagnose_bird
done
```
**Record:** pass@1 (strict + BIRD) per source; `where_mismatch` / format-bucket movement;
per-question prompt-token cost (long descriptions inflate the prompt). Replicate-or-refute
the paper's *profiling > supplied* finding, plainly.

### 2B. #141 — literal→field steering

```bash
# Off vs on, same generator (repeat for strong + weak):
LITERAL_STEER=0 RUN_CONFIG=accuracy uv run python -m eval.eval_bird_rag
LITERAL_STEER=1 RUN_CONFIG=accuracy uv run python -m eval.eval_bird_rag
```
**Record:** pass@1 (strict + BIRD); the `ambiguous_column` / `where_mismatch` subset
movement (`diagnose_bird`); **trigger rate** (literals off-column), **recovery rate**
(rephrase fixed it), **false-steer rate** (on-column literal the sample missed), and
added retries.

### 2C. #138 — task-alignment schema linking *(after wiring `LINK_STRATEGY`)*

```bash
RUN_CONFIG=accuracy                       uv run python -m eval.eval_bird_rag   # lexical RAG
LINK_STRATEGY=task_alignment RUN_CONFIG=accuracy uv run python -m eval.eval_bird_rag
```
**Record:** retrieval **recall** and pass@1 (strict + BIRD) for both; table-selection
bucket (`missing_table` / `extra_table` / `spurious_join`) movement; the extra
per-question generation cost (linking spends N extra generations, folded into the run's
totals); and the recall-vs-perfect-linking ceiling.

### 2D. #139 — bad-construction soundness checks *(after wiring `SOUNDNESS` toggle)*

```bash
# Meaningful at pass@k (the checks feed back within the retry budget):
RETRY_BUDGET=3 SOUNDNESS=0 RUN_CONFIG=accuracy uv run python -m eval.eval_bird_selfcorrect
RETRY_BUDGET=3 SOUNDNESS=1 RUN_CONFIG=accuracy uv run python -m eval.eval_bird_selfcorrect
```
**Record:** pass@1 (unchanged) and pass@k ± the checks; `where_mismatch` / projection /
ordering bucket movement (**not** the table-selection cluster — a different bucket than
#138); added retries. Honest-null clause: on flash-class generators the precision buckets
are already near-zero (#117), so the live lift may be ~0 even at the fixture's 1.000 catch
rate — the fixture rate is the durable result.

### 2E. #142 — result-set majority voting *(after wiring `eval/eval_bird_vote.py`)*

```bash
# Twin: attempt-1 vs majority-of-k, same k, on strong AND weak:
K=3 RUN_CONFIG=accuracy                                   uv run python -m eval.eval_bird_vote
K=3 MODEL=openrouter/moonshotai/kimi-k2.7-code            uv run python -m eval.eval_bird_vote
```
**Record:** twin **pass@1 (attempt-1) vs pass@k (majority-selected)** for both generators;
the **vote-agreement distribution** (unanimous / majority / no-majority — the diagnostic
that explains the gap); k× generation + execution cost (tokens, wall-clock); and an
explicit comparison to the **self-correct selector at the same k** (additive, redundant,
or worse — state it plainly). Expect an honest null on the strong generator (candidates
agree → vote is a no-op); the value, if any, lives on the weak one.

---

## 3. Generators & slices (the strong/weak contrast)

| Role | Config | Why |
|---|---|---|
| **Strong** | `RUN_CONFIG=accuracy` → `gemini-3.5-flash` + `MAX_TOKENS=4096` | Top-of-slice (#124); where levers often no-op — the honest-null case. |
| **Weak** | `MODEL=openrouter/moonshotai/kimi-k2.7-code` | The Step-5 weak generator; where self-correction and voting found their lift. |
| **Cheap iter** | `MODEL=openrouter/google/gemini-3.1-flash-lite` | Matches sonnet at ~1/12 cost; use to shake out wiring before spending on the real arms. |

**Slices:** iterate on **dev** (50); confirm a lift on **`dev-wide`** (250, ±0.031 SE, so
a +0.03 effect is visible); spend the **`holdout`** (100) shot **once** per lever that
earned a dev-wide lift.

---

## 4. Recording discipline (replace the pending rows)

For each measured number: append/replace a `RESULTS.md` row —
`date | 12 (#NNN) | metric | number | model | slice | prompt version | commit` — and a
one-paragraph honest reading (including nulls and their *why*). Every reproduce command
above goes in that entry. Do **not** report a number without its row and commit.

## 5. Suggested order (cheapest signal first, hold the held-out shot)

1. **#141 literal-steer** — already wired, no precompute; cheapest to run, targets a named
   bucket. Fast confidence the live harness is sound.
2. **#140 profiling** — the paper's headline and biggest potential lift; do the precompute
   once, then the three-way source A/B.
3. **#138 linking** — after `LINK_STRATEGY` wiring; the retrieval-recall lever for the
   table-selection frontier.
4. **#139 soundness** and **#142 voting** — the two most likely honest nulls on a strong
   generator; run them on the **weak** generator too, where their value (if any) lives.

Hold every `holdout` run until its lever shows a `dev-wide` lift above the ±0.031 floor.
