"""Measure the guardrail gate against the red-team fixture.

The deterministic guard (``src/nl2sql/pipeline/guard.py``) is a *measured*
feature: its worth is a number — "caught N% of red-team queries" — not a claim.
This module is that measurement harness, a peer of the comparator's golden-fixture
proof. It loads the labeled ``(candidate SQL, expected verdict)`` cases under
``fixtures/redteam_guard/``, runs each through ``guard_sql``, and aggregates:

- **verdict agreement** — did the gate match every case's expected verdict (the
  unit-test contract, including the benign allows), and
- **catch rate** — of the *dangerous* cases (those labeled ``reject``), what
  fraction did the gate actually reject. This is the headline safety number
  appended to ``RESULTS.md`` at the close of Step 4.

Deterministic and offline — no DB, no network. The gate itself is sqlglot-AST
only (CLAUDE.md §4, §7); this just scores it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2sql.pipeline.guard import GuardDecision, guard_sql

# The fixture lives at the repo-root ``fixtures/redteam_guard/`` dir; eval/ sits
# directly under the repo root.
DEFAULT_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "redteam_guard"
)

# Per-case default when a case omits ``dialect``; BIRD (SQLite) drives the
# headline numbers, and the dangerous constructs are SQLite-expressible.
DEFAULT_CASE_DIALECT = "sqlite"


@dataclass(frozen=True)
class CaseOutcome:
    """One red-team case scored: what the gate did vs. what the fixture expects."""

    case_id: str
    expected_verdict: str
    actual_verdict: str
    expected_rule: str | None = None
    actual_rule: str | None = None

    @property
    def is_dangerous(self) -> bool:
        """A case is part of the red-team set iff it is *expected* to be rejected."""
        return self.expected_verdict == GuardDecision.REJECT.value

    @property
    def verdict_matches(self) -> bool:
        """Did the gate's verdict match the fixture (allow stays allowed too)?"""
        return self.actual_verdict == self.expected_verdict

    @property
    def caught(self) -> bool:
        """A dangerous case the gate actually rejected."""
        return self.is_dangerous and self.actual_verdict == GuardDecision.REJECT.value

    @property
    def rule_matches(self) -> bool:
        """When the fixture pins a rule, did that rule fire? (True if unpinned.)"""
        return self.expected_rule is None or self.actual_rule == self.expected_rule


@dataclass(frozen=True)
class RedTeamReport:
    """Aggregate of the gate over the red-team fixture: agreement + catch rate."""

    outcomes: tuple[CaseOutcome, ...]

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def n_dangerous(self) -> int:
        return sum(1 for o in self.outcomes if o.is_dangerous)

    @property
    def n_caught(self) -> int:
        return sum(1 for o in self.outcomes if o.caught)

    @property
    def catch_rate(self) -> float:
        """Fraction of dangerous cases rejected; 0.0 over an empty red-team set."""
        return self.n_caught / self.n_dangerous if self.n_dangerous else 0.0

    @property
    def all_verdicts_match(self) -> bool:
        """Every case (dangerous and benign) landed on its expected verdict."""
        return all(o.verdict_matches for o in self.outcomes)

    @property
    def all_rules_match(self) -> bool:
        """Every pinned reject fired via the expected rule."""
        return all(o.rule_matches for o in self.outcomes)

    def mismatches(self) -> list[CaseOutcome]:
        """Cases whose verdict or pinned rule disagreed with the fixture."""
        return [o for o in self.outcomes if not (o.verdict_matches and o.rule_matches)]


def load_cases(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> list[dict[str, Any]]:
    """Load every red-team case from the fixture dir, in stable (file, order) order."""
    cases: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        data = json.loads(path.read_text())
        for case in data["cases"]:
            cases.append({"_file": path.stem, **case})
    return cases


def run_case(case: dict[str, Any]) -> CaseOutcome:
    """Run one fixture case through ``guard_sql`` and score it against its label."""
    dialect = case.get("dialect", DEFAULT_CASE_DIALECT)
    result = guard_sql(case["sql"], dialect=dialect)
    return CaseOutcome(
        case_id=case["id"],
        expected_verdict=case["expected_verdict"],
        actual_verdict=result.decision.value,
        expected_rule=case.get("expected_rule"),
        actual_rule=result.rule,
    )


def evaluate(cases: Iterable[dict[str, Any]]) -> RedTeamReport:
    """Score a batch of fixture cases into a ``RedTeamReport``."""
    return RedTeamReport(tuple(run_case(case) for case in cases))


def summary_lines(report: RedTeamReport) -> Sequence[str]:
    """Human-readable summary — the catch rate plus any verdict mismatches."""
    lines = [
        f"red-team catch rate: {report.catch_rate:.3f}  "
        f"({report.n_caught}/{report.n_dangerous} dangerous queries caught)",
        f"verdict agreement: {report.total - len(report.mismatches())}/{report.total}",
    ]
    for o in report.mismatches():
        lines.append(
            f"  MISMATCH {o.case_id}: expected {o.expected_verdict}"
            f"/{o.expected_rule} got {o.actual_verdict}/{o.actual_rule}"
        )
    return lines


def _main() -> None:
    """Dev entry: print the catch rate over the committed fixture."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = evaluate(load_cases())
    for line in summary_lines(report):
        print(line)


if __name__ == "__main__":
    _main()
