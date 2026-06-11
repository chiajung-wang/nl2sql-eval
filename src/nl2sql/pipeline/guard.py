"""Stage: guard — deterministic, pre-execution sqlglot AST gate.

The guardrail gate sits between ``generate`` and ``execute`` and statically vets
the candidate SQL **before** it ever touches a database. It is deterministic by
construction: every check is an assertion about the sqlglot AST — never a regex
over the SQL text, never an LLM judge (CLAUDE.md §4, §7). That is the whole point
— a safety-critical check must be testable and reproducible, which is why the
gate is *measured* against ``fixtures/redteam_guard/``.

Checks land incrementally across Step 4:

- **read-only enforcement** (this issue) — reject writes/DDL by statement type;
- **dangerous-op blocking** (Step 4, next issue) — stacked statements, ATTACH,
  write-bearing PRAGMA and other side-effecting meta-commands;
- **cost/complexity heuristic** (Step 4) — join count, missing ``LIMIT``,
  cartesian products, all read off the AST (heuristic-first; no EXPLAIN on the
  SQLite path).

**Table-scope** enforcement is deliberately *not* here: it needs a per-db
allowed-tables list, which is schema metadata formalized in Step 6. It arrives
when its data source is real, not hardcoded provisionally now.

Two public surfaces:

- ``guard_sql`` — the pure, deterministic core. Takes SQL, returns a
  ``GuardResult``. This is what the red-team fixture and unit tests drive.
- ``guard`` — the thin pipeline stage. Wraps ``guard_sql``, records the verdict
  on the ``RunState``, and emits an obs span (mirroring ``execute``). The harness
  reads the recorded verdict to classify a rejected run as ``GUARDRAIL_REJECTED``
  — the *classifier* stays in the harness, never here (CLAUDE.md §3).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from nl2sql.obs import stage_span
from nl2sql.pipeline.generate import DEFAULT_DIALECT
from nl2sql.pipeline.state import RunState

logger = logging.getLogger(__name__)


class GuardDecision(StrEnum):
    """The deterministic verdict for one candidate: run it, or don't."""

    ALLOW = "allow"
    REJECT = "reject"


@dataclass(frozen=True)
class GuardResult:
    """A guard verdict: the decision plus, on a reject, which rule and why.

    ``rule`` is the machine-readable check that fired (e.g. ``"read_only"``,
    ``"parse_error"``); ``reason`` is the human-readable explanation. Both are
    ``None`` on an allow. ``note`` composes them for the harness/log without ever
    carrying result rows — the candidate SQL is generated text (no raw PII).
    """

    decision: GuardDecision
    rule: str | None = None
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is GuardDecision.ALLOW

    @property
    def rejected(self) -> bool:
        return self.decision is GuardDecision.REJECT

    @property
    def note(self) -> str | None:
        """``"rule: reason"`` for explainability; ``None`` on a bare allow."""
        if self.rule is None:
            return self.reason
        return f"{self.rule}: {self.reason}" if self.reason else self.rule


# Statement AST types that mutate data or schema. Read-only enforcement keys off
# the parsed statement *type* — not a keyword regex — so an ``INSERT`` hiding in
# a CTE name or a comment cannot slip past, and a column literally named
# ``"delete"`` cannot trip a false positive. ``Create`` covers CREATE ... AS
# SELECT; ``Merge`` is a write; ``TruncateTable`` is DDL-adjacent data loss.
_WRITE_DDL_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
)


# The pipeline names dialects for the *prompt* ("PostgreSQL", "SQLite"); sqlglot
# wants its own keys ("postgres", "sqlite"). Map the names we use; anything
# unrecognized parses dialect-agnostically (``None``) rather than raising.
_DIALECT_ALIASES: dict[str, str] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "sqlite": "sqlite",
    "mysql": "mysql",
    "bigquery": "bigquery",
}


def _normalize_dialect(dialect: str) -> str | None:
    """Map a prompt dialect name to a sqlglot dialect key, or ``None`` if unknown."""
    return _DIALECT_ALIASES.get(dialect.strip().lower())


def _parse_statements(sql: str, dialect: str) -> list[exp.Expression] | None:
    """Split ``sql`` into statements, trying the named dialect then the generic
    parser. Returns ``None`` only if the SQL parses under neither — a candidate
    the gate cannot prove safe."""
    normalized = _normalize_dialect(dialect)
    attempts = (normalized,) if normalized is None else (normalized, None)
    for parse_dialect in attempts:
        try:
            return [
                s for s in sqlglot.parse(sql, dialect=parse_dialect) if s is not None
            ]
        except ParseError:
            continue
    return None


def _check_read_only(statements: Sequence[exp.Expression], dialect: str) -> str | None:
    """Reject if any statement writes data or changes schema (DML/DDL).

    Side-effecting meta-commands that are neither DML nor DDL (ATTACH, PRAGMA,
    stacked statements) are a distinct attack surface handled by the dangerous-op
    rule in the next Step-4 issue — not silently folded in here.
    """
    for stmt in statements:
        if isinstance(stmt, _WRITE_DDL_TYPES):
            kind = type(stmt).__name__.upper()
            return f"{kind} mutates data or schema; the gate is read-only"
    return None


# A guard rule: inspect the parsed statements (already split per ``;``) and the
# dialect, return a reject reason or ``None`` to pass. Rules are pure functions
# of the AST — the registry mirrors ``eval.compare``'s rule pipeline so later
# Step-4 checks slot in without touching the gate's control flow.
GuardRule = Callable[[Sequence[exp.Expression], str], str | None]

_RULES: dict[str, GuardRule] = {
    "read_only": _check_read_only,
}

# The checks run, in order, on every candidate. Later Step-4 issues append
# "dangerous_op" and "cost" here; the first rule to fire wins (fail-fast).
DEFAULT_GUARD_RULES: tuple[str, ...] = ("read_only",)


def guard_sql(
    sql: str | None,
    *,
    dialect: str = DEFAULT_DIALECT,
    rules: Sequence[str] = DEFAULT_GUARD_RULES,
) -> GuardResult:
    """Statically vet candidate SQL; the deterministic core of the gate.

    Parses ``sql`` into one-or-more statements with sqlglot and runs each named
    rule until one rejects. Returns the first reject, or ``ALLOW`` if every rule
    passes.

    Two boundary cases:

    - **No SQL** (``None``/blank) is *not* a guard concern — there is nothing to
      run. It allows through so ``execute`` records the missing-SQL outcome as it
      always has (an ``EXECUTION_ERROR_FINAL``), keeping generation gaps distinct
      from safety rejections in the terminal-state mix.
    - **Unparseable SQL** is rejected (``parse_error``): SQL the gate cannot parse
      is SQL it cannot prove safe, and a parser that diverges from the engine's
      could otherwise wave a write through. Default-deny is the safe stance; the
      distinct ``rule`` keeps it separable from genuine attack catches in
      analysis.
    """
    if not sql or not sql.strip():
        return GuardResult(GuardDecision.ALLOW)

    statements = _parse_statements(sql, dialect)
    if not statements:
        return GuardResult(
            GuardDecision.REJECT,
            rule="parse_error",
            reason="candidate did not parse under the named or generic dialect",
        )

    for name in rules:
        violation = _RULES[name](statements, dialect)
        if violation is not None:
            return GuardResult(GuardDecision.REJECT, rule=name, reason=violation)

    return GuardResult(GuardDecision.ALLOW)


def guard(
    state: RunState,
    *,
    dialect: str = DEFAULT_DIALECT,
    rules: Sequence[str] = DEFAULT_GUARD_RULES,
) -> RunState:
    """Pipeline stage: vet ``state.candidate_sql`` and record the verdict.

    On a reject, sets ``state.guard_rejected``/``state.guard_reason`` so the
    harness buckets the run as ``GUARDRAIL_REJECTED`` and skips execution; on an
    allow, leaves the state untouched for ``execute``. Only the decision and rule
    (never row values) are attached to the obs span. Mutates and returns
    ``state``.
    """
    with stage_span("guard", db_id=state.db_id) as extra:
        result = guard_sql(state.candidate_sql, dialect=dialect, rules=rules)
        extra["decision"] = result.decision.value
        if result.rejected:
            state.guard_rejected = True
            state.guard_reason = result.note
            extra["rule"] = result.rule
    return state
