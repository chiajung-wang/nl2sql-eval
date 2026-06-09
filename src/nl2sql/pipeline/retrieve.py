"""Stage: retrieve — schema-RAG over table/column metadata + sample values.

Loop-aware: re-triggered on column/table-not-found errors. Arrives at Step 6;
before that, the full schema is dumped inline by ``generate``.

Stub — implemented in docs/plans/step-6.
"""
