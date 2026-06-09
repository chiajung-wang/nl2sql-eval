"""Batch runner: question → result, scored and bucketed.

For each question: run the pipeline, score via canonicalized result-set
comparison (upstream of redaction), classify the terminal state, and record
cost/latency/attempts. Reports pass@1 and pass@k and retrieval recall. The
terminal-state classifier lives here, not in ``state.py``.

Stub — implemented in docs/plans/step-3 onward.
"""
