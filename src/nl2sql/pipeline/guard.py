"""Stage: guard — deterministic, pre-execution sqlglot AST gate.

Checks (Step 4+): read-only enforcement, dangerous-op blocking, cost/complexity
heuristic (heuristic-first; EXPLAIN only where supported), and per-db
table-scope. No regex for SQL semantics, no LLM calls — sqlglot ASTs only. On
fail: reject or feed back as a correction signal.

Stub — implemented in docs/plans/step-4 (and table-scope in step-6).
"""
