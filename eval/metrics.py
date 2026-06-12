"""Aggregate metrics over a scored batch — pass@1 / pass@k and the terminal mix.

The batch runner (``eval/harness.py``) scores each question and hands the
per-case verdicts here for aggregation. Accuracy on a single batch is reported by
:class:`BatchReport`; the Step-5 **twin metric** — pass@1 (correction off) vs
pass@k (correction on), the gap, and the added cost/latency that buys it — is
:class:`TwinReport` over two batches of the same slice. Retrieval recall arrives
with Step 6. The terminal-state *classifier* lives in the harness (CLAUDE.md §3)
— this module only *aggregates* the already classified, scored results, and never
holds row values (scoring is upstream of redaction, §5.2/§5.3).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from eval.cost import cost_usd
from nl2sql.pipeline.state import TerminalState


@dataclass(frozen=True)
class CaseResult:
    """One scored question: how it bucketed, whether it was correct, and its cost.

    ``note`` carries the comparator's reason or the error text for explainability
    — never the result rows, which could leak raw PII into a report or log.
    ``attempts``/``input_tokens``/``output_tokens``/``latency_ms`` are the
    per-question cost of the run (Step 5) — ``attempts`` is how many
    generate→execute cycles the correction loop spent, so a recovery is never
    "free" in the aggregate.
    """

    case_id: str
    db_id: str
    terminal_state: TerminalState
    correct: bool
    difficulty: str | None = None
    candidate_sql: str | None = None
    note: str | None = None
    attempts: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


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
    def accuracy(self) -> float:
        """Fraction correct over the batch; 0.0 over an empty batch.

        Mode-neutral: this is pass@1 for a correction-off batch and pass@k for a
        correction-on one — :class:`TwinReport` labels each by how it was run.
        """
        return self.n_correct / self.total if self.total else 0.0

    # pass@1 is ``accuracy`` for the single-shot (correction-off) batch; kept as a
    # named alias so the Step-3 BIRD runner and summary keep reading the same field.
    pass_at_1 = accuracy

    @property
    def total_attempts(self) -> int:
        return sum(r.attempts for r in self.results)

    @property
    def mean_attempts(self) -> float:
        return self.total_attempts / self.total if self.total else 0.0

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.results)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.results)

    @property
    def total_latency_ms(self) -> float:
        return sum(r.latency_ms for r in self.results)

    @property
    def mean_latency_ms(self) -> float:
        return self.total_latency_ms / self.total if self.total else 0.0

    def cost_usd(self, model: str) -> float | None:
        """Total USD cost of the batch on ``model`` (``None`` if unpriced).

        Linear in tokens, so the per-case sum equals pricing the batch totals.
        """
        return cost_usd(model, self.total_input_tokens, self.total_output_tokens)

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


def summary_lines(report: BatchReport) -> list[str]:
    """The aggregate summary of a batch — pass@1, terminal mix, by-difficulty.

    Shared by the live entrypoints so payments and BIRD print the same shape.
    Aggregates only (no row values).
    """
    lines = [
        f"pass@1: {report.pass_at_1:.3f}  ({report.n_correct}/{report.total})",
        "terminal states:",
    ]
    lines += [
        f"  {state.value:24} {count}"
        for state, count in report.terminal_counts().items()
        if count
    ]
    lines.append("pass@1 by difficulty:")
    lines += [
        f"  {str(difficulty):24} {rate:.3f}"
        for difficulty, rate in sorted(
            report.pass_at_1_by("difficulty").items(), key=lambda kv: str(kv[0])
        )
    ]
    return lines


@dataclass(frozen=True)
class TwinReport:
    """The Step-5 headline: pass@1 vs pass@k over the *same* slice, and its price.

    ``pass1`` is the slice run with correction off (single shot); ``passk`` is the
    same slice with the capped correction budget on. The gap between them is what
    self-correction is worth; ``recovery_rate``, ``added_latency_ms``, and
    ``added_cost_usd`` quantify the trade — "recovers X% of initial failures at a
    cost of Y". ``model`` prices both batches (the budget is a real-dollars lever).

    Built from two :class:`BatchReport`s of the *same questions* — the per-case
    alignment for ``recovery_rate`` is by ``case_id``.
    """

    pass1: BatchReport
    passk: BatchReport
    model: str

    @property
    def pass_at_1(self) -> float:
        return self.pass1.accuracy

    @property
    def pass_at_k(self) -> float:
        return self.passk.accuracy

    @property
    def gap(self) -> float:
        """pass@k − pass@1 — the accuracy the correction loop adds."""
        return self.pass_at_k - self.pass_at_1

    @property
    def recovery_rate(self) -> float:
        """Of the questions pass@1 got wrong, the fraction pass@k recovers.

        0.0 when pass@1 already passed everything (nothing to recover).
        """
        passk_correct = {r.case_id for r in self.passk.results if r.correct}
        failed_at_1 = [r for r in self.pass1.results if not r.correct]
        if not failed_at_1:
            return 0.0
        recovered = sum(1 for r in failed_at_1 if r.case_id in passk_correct)
        return recovered / len(failed_at_1)

    @property
    def added_attempts(self) -> int:
        """Extra generate→execute cycles pass@k spent over pass@1's one-per-case."""
        return self.passk.total_attempts - self.pass1.total_attempts

    @property
    def added_latency_ms(self) -> float:
        return self.passk.total_latency_ms - self.pass1.total_latency_ms

    @property
    def added_cost_usd(self) -> float | None:
        """pass@k − pass@1 total USD; ``None`` if the model is unpriced."""
        k = self.passk.cost_usd(self.model)
        one = self.pass1.cost_usd(self.model)
        if k is None or one is None:
            return None
        return k - one


def twin_summary_lines(twin: TwinReport) -> list[str]:
    """Plain-language pass@1→pass@k summary: the gap and the cost that buys it."""
    n = twin.pass1.total
    lines = [
        f"pass@1: {twin.pass_at_1:.3f}  ({twin.pass1.n_correct}/{n})",
        f"pass@k: {twin.pass_at_k:.3f}  ({twin.passk.n_correct}/{n})",
        f"gap (pass@k − pass@1): {twin.gap:+.3f}",
        f"recovery of initial failures: {twin.recovery_rate:.3f}",
        f"added attempts: {twin.added_attempts}  (pass@k total "
        f"{twin.passk.total_attempts} vs pass@1 {twin.pass1.total_attempts})",
        f"added latency: {twin.added_latency_ms:+.1f} ms total",
    ]
    added_cost = twin.added_cost_usd
    if added_cost is None:
        lines.append(f"added cost: unavailable (no price for {twin.model})")
    else:
        lines.append(f"added cost: ${added_cost:+.6f} ({twin.model})")
    return lines
