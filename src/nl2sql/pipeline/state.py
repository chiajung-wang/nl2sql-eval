"""Shared pipeline run state and the terminal-state enum.

Per the architecture rules, this module holds the run-state dataclass and the
*full* terminal-state enum only. The classifier that decides which terminal
state a run lands in lives in the harness, never here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TerminalState(StrEnum):
    """Every run buckets into exactly one of these.

    Only ``SUCCESS`` and ``EXECUTION_ERROR_FINAL`` are reachable in Step 1; the
    full set is defined now so later steps never reshape this module.
    """

    SUCCESS = "success"
    WRONG_ANSWER = "wrong_answer"
    RETRY_EXHAUSTED = "retry_exhausted"
    EXECUTION_ERROR_FINAL = "execution_error_final"
    GUARDRAIL_REJECTED = "guardrail_rejected"
    RETRIEVAL_EMPTY = "retrieval_empty"


@dataclass
class RunState:
    """Mutable state threaded through the pipeline for a single question.

    The db identity is an input (single-db per run); fields below are populated
    as the run advances through retrieve → generate → guard → execute → correct.
    """

    question: str
    db_id: str

    # Populated as the run progresses.
    candidate_sql: str | None = None
    result_rows: list[tuple[Any, ...]] | None = None
    result_columns: list[str] | None = None
    error: str | None = None
    attempts: int = 0
    terminal_state: TerminalState | None = None

    # Schema-RAG (Step 6). The relevant table names the ``retrieve`` stage
    # selected for this question (declaration order). The harness scores
    # **retrieval recall** of these against the gold query's actual tables; the
    # focused schema rendered from them is what ``generate`` sees instead of the
    # full dump. ``None`` until retrieval runs (the naive-dump path leaves it so).
    retrieved_tables: list[str] | None = None

    # Adaptive retrieval gate (Step 6 follow-up, #76). Which branch the gate took
    # this run: ``"full"`` (the whole schema fit the configured schema-token
    # budget, so it was dumped — no retrieval, no dropped tables) or ``"rag"`` (the
    # schema exceeded the budget, so the relevant tables were retrieved). ``None``
    # when the gate is off (no budget configured) or on the naive-dump path that
    # never calls ``retrieve``. Surfaced on the span so a trace shows *why* a given
    # schema was sent.
    retrieval_mode: str | None = None

    # Self-correction loop (Step 5). ``max_attempts`` is the capped retry budget
    # the graph runs the generate→execute cycle under (1 = single-shot, no
    # correction — the pass@1 mode). ``attempts`` counts cycles actually run.
    # ``correction`` carries the prior failed attempt's SQL + error text that the
    # next ``generate`` feeds back into the prompt; ``None`` on the first attempt.
    # The classifier (in the harness, never here) reads ``attempts`` to split a
    # budget-exhausted run (RETRY_EXHAUSTED) from a single-shot failure
    # (EXECUTION_ERROR_FINAL).
    max_attempts: int = 1
    correction: dict[str, str] | None = None

    # Set by the guard stage when a candidate fails a pre-execution check; the
    # harness reads these to bucket the run as GUARDRAIL_REJECTED (the classifier
    # lives in the harness, not here). ``guard_reason`` is "rule: why" — no rows.
    # ``guard_rule`` is the machine-readable rule that fired, so the graph can
    # treat a table-scope rejection as a re-retrieval signal (CLAUDE.md §5.4)
    # rather than a hard stop, while a security rule (read_only/…) ends the run.
    guard_rejected: bool = False
    guard_reason: str | None = None
    guard_rule: str | None = None

    # Free-form per-stage diagnostics; cost/latency/tokens land here later.
    meta: dict[str, Any] = field(default_factory=dict)
