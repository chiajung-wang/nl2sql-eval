"""Aggregate metrics over a scored batch — pass@1 and the terminal-state mix.

The batch runner (``eval/harness.py``) scores each question and hands the
per-case verdicts here for aggregation. With no self-correction yet, **pass@1**
is the only meaningful accuracy metric this step; pass@k arrives with the Step-5
retry loop, retrieval recall with Step-6. The terminal-state *classifier* lives
in the harness (CLAUDE.md §3) — this module only *aggregates* the already
classified, scored results, and never holds row values (scoring is upstream of
redaction, §5.2/§5.3).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from nl2sql.pipeline.state import TerminalState


@dataclass(frozen=True)
class CaseResult:
    """One scored question: how it bucketed and whether it was correct.

    ``note`` carries the comparator's reason or the error text for explainability
    — never the result rows, which could leak raw PII into a report or log.
    """

    case_id: str
    db_id: str
    terminal_state: TerminalState
    correct: bool
    difficulty: str | None = None
    candidate_sql: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class BatchReport:
    """Aggregate view of a scored batch: pass@1 and the terminal-state mix."""

    results: tuple[CaseResult, ...]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def n_correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def pass_at_1(self) -> float:
        """Fraction correct on the single first attempt; 0.0 over an empty batch."""
        return self.n_correct / self.total if self.total else 0.0

    def terminal_counts(self) -> dict[TerminalState, int]:
        """Count of runs in each terminal state — every state present (0 if none)."""
        counts = Counter(r.terminal_state for r in self.results)
        return {state: counts.get(state, 0) for state in TerminalState}

    def pass_at_1_by(self, attr: str) -> dict[str | None, float]:
        """pass@1 grouped by a ``CaseResult`` attribute (e.g. ``"difficulty"``)."""
        groups: dict[str | None, list[CaseResult]] = {}
        for r in self.results:
            groups.setdefault(getattr(r, attr), []).append(r)
        return {
            key: sum(1 for r in rs if r.correct) / len(rs) for key, rs in groups.items()
        }
