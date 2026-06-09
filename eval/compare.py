"""Canonicalization + result-set comparison (the proven scorer).

Execution accuracy via canonicalized result-set comparison, never SQL
string-match — two different queries can be equally correct. Deterministic; no
LLM judge. Proven against the golden fixture of (gold, candidate, verdict)
triples. One of the two heavily-tested deterministic cores.

Stub — implemented in docs/plans/step-2.
"""
