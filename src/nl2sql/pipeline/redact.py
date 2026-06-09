"""Stage: redact — column-aware PII masking, post-scoring.

Deterministic and schema-driven. Runs *after* the harness scores the raw
verified result; only the redacted (presented) result is shown to users or
written to logs/traces. Raw PII never reaches logs. Arrives at Step 8.

Stub — implemented in docs/plans/step-8.
"""
