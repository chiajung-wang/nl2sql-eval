# Plan — Step 6: Schema-RAG + loop-aware re-trigger + retrieval-recall + table-scope guardrail

**Phase:** Measured features
**Headline:** Quantify what retrieval is worth — and measure the failure mode that can't be fixed at runtime.

## Goal
Add RAG over **schema metadata** (not documents), make it **loop-aware**, add the **retrieval-recall** eval axis, complete the guardrail with **table-scope enforcement** (whose data source now exists), and expand the slice to **large-schema** dbs to show the retrieval lift where it matters.

## Prerequisites
- Step 3 (harness/slice), Step 4 (guard gate), Step 5 (correction loop to hook re-trigger into).

## What to build
1. **`schema_index/` + `pipeline/retrieve.py`** — index table definitions, column names/types, **a few sample values per column** (knowing `status` ∈ {failed, settled} changes the SQL), optional short descriptions. Retrieve only the relevant tables for *this* question instead of dumping the full schema.
2. **Loop-aware re-trigger** — a `column/table-not-found` execution error feeds back into **retrieval** (re-retrieve with the error as signal), not only into generation. This closes the asymmetry where everything else looped but retrieval was single-shot.
3. **Retrieval-recall metric** (`metrics.py`) — recall of retrieved tables vs the **gold query's actual tables**. This is how the *silent* wrong-schema failure (valid SQL, wrong tables, no error, wrong-but-unsuspicious answer) gets **measured** even though it can't be fixed at runtime.
4. **Table-scope guardrail** (`guard.py`) — now add "touches tables it shouldn't" using the per-db allowed-tables list that schema metadata makes available (deferred here from Step 4 deliberately).
5. **Slice expansion** — extend the frozen BIRD slice to include **large-schema** dbs (still seeded/committed/stratified). This is where retrieval earns its keep vs the Step 3 naive baseline.

## Done when
- Retrieval recall is reported alongside accuracy.
- The loop re-retrieves on not-found errors.
- The **retrieval lift** (accuracy with retrieval vs the Step 3 naive-dump baseline) is recorded.

## Results log
Append the **retrieval-recall** number and, crucially, the **naive-baseline → retrieval lift** (before/after accuracy) with config + commit. This is the second of the two sharpest findings.

## Pitfalls
- The silent wrong-schema case has no clean runtime fix — don't pretend to fix it; **measure** it (retrieval recall). Trying to "fix" it is trying to solve Text-to-SQL.
- Keep the slice frozen/seeded/stratified even as you expand it, or CI deltas become noisy.
- Build retrieval even though the payments demo is small enough not to need it — it's a deliberate design choice you want to demonstrate, and BIRD's large dbs genuinely need it.
