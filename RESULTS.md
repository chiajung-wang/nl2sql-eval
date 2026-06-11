# RESULTS

The committed running results log. **A step is not done until its number is
appended here** with the exact config that produced it: every reported number
must be traceable to its config and commit (CLAUDE.md §6, PRD §10).

Capture especially the **pass@1 → pass@k gap** (Step 5, what self-correction is
worth) and the **naive-baseline → schema-RAG retrieval lift** plus **retrieval
recall** (Step 6).

## Log

| Date | Step | Metric | Number | Model | Slice ID | Prompt version | Commit |
| ---- | ---- | ------ | ------ | ----- | -------- | -------------- | ------ |
| 2026-06-11 | 3 | pass@1 | 0.420 (21/50) | claude-sonnet-4-6 | step3-naive-schema-dump-baseline | generate/v2 | 5d9d8ae |
