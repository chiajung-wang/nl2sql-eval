"""Stage wiring: the hand-rolled state machine.

Step 1 (issue 4) wires a linear ``generate → execute → return``. Conditional
edges (guard, correct, loop-aware retrieve) arrive in later steps; LangGraph
swaps in at Step 7 only after the logic is proven.

Stub — implemented in docs/plans/step-1/issue-4.
"""
