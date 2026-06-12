"""Stage: guard — deterministic, pre-execution sqlglot AST gate.

The guardrail gate sits between ``generate`` and ``execute`` and statically vets
the candidate SQL **before** it ever touches a database. It is deterministic by
construction: every check is an assertion about the sqlglot AST — never a regex
over the SQL text, never an LLM judge (CLAUDE.md §4, §7). That is the whole point
— a safety-critical check must be testable and reproducible, which is why the
gate is *measured* against ``fixtures/redteam_guard/``.

Checks land incrementally across Step 4:

- **read-only enforcement** — reject writes/DDL by statement type;
- **dangerous-op blocking** — stacked statements, ATTACH/DETACH, PRAGMA and other
  side-effecting meta-commands;
- **cost/complexity heuristic** — join count, unbounded ``SELECT *``, cartesian
  products, all read off the AST (heuristic-first; no EXPLAIN on the SQLite path).

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

# A write whose syntax sqlglot does not model lands in a generic ``exp.Command``
# rather than a typed node — SQLite's ``REPLACE INTO`` (an INSERT-or-replace) is
# the live example on the BIRD path. We key off the parsed command verb (an AST
# field, still not a text regex) so this data write cannot pass as read-only.
# Non-write meta-commands (ATTACH, PRAGMA, VACUUM, EXPLAIN, stacked statements)
# are a *separate* attack surface owned by the dangerous-op rule — read-only's
# scope is strictly data/schema writes.
_WRITE_COMMANDS: frozenset[str] = frozenset({"REPLACE"})


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


def _is_empty_statement(stmt: exp.Expression | None) -> bool:
    """A node that carries no query: a ``None`` slot or a bare ``;`` / trailing
    comment, which sqlglot models as an empty ``Semicolon``. These are not
    statements and must not inflate the stacked-query count."""
    return stmt is None or isinstance(stmt, exp.Semicolon)


def _parse_statements(sql: str, dialect: str) -> list[exp.Expression] | None:
    """Split ``sql`` into real statements, trying the named dialect then the
    generic parser. Empty/trailing-comment nodes are dropped so a single query
    with a trailing ``;`` or comment is not mistaken for a stacked pair. Returns
    ``None`` only if the SQL parses under neither dialect — a candidate the gate
    cannot prove safe."""
    normalized = _normalize_dialect(dialect)
    attempts = (normalized,) if normalized is None else (normalized, None)
    for parse_dialect in attempts:
        try:
            parsed = sqlglot.parse(sql, dialect=parse_dialect)
        except ParseError:
            continue
        return [s for s in parsed if not _is_empty_statement(s)]
    return None


def _check_read_only(statements: Sequence[exp.Expression], dialect: str) -> str | None:
    """Reject if any statement writes data or changes schema (DML/DDL).

    ``find`` walks each statement's whole subtree (self included), so a write
    smuggled inside a CTE — ``WITH x AS (DELETE ... RETURNING *) SELECT ...`` —
    is caught, not just a top-level one. Writes sqlglot parses as a generic
    ``Command`` (SQLite ``REPLACE INTO``) are caught by verb.

    Side-effecting meta-commands that are neither DML nor DDL (ATTACH, PRAGMA,
    stacked statements) are a distinct attack surface owned by the dangerous-op
    rule — not silently folded in here.
    """
    for stmt in statements:
        write = stmt.find(*_WRITE_DDL_TYPES)
        if write is not None:
            kind = type(write).__name__.upper()
            return f"{kind} mutates data or schema; the gate is read-only"
        if isinstance(stmt, exp.Command) and stmt.name.upper() in _WRITE_COMMANDS:
            return f"{stmt.name.upper()} writes data; the gate is read-only"
    return None


# Typed meta-statements that escape the data boundary or alter engine state —
# never DML/DDL, so read-only lets them by, but never a legitimate answer to a
# question either. ``Attach``/``Detach`` reach across databases; ``Pragma`` flips
# engine flags (``PRAGMA writable_schema=ON`` is the classic read-only bypass).
_DANGEROUS_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Attach,
    exp.Detach,
    exp.Pragma,
)


def _check_dangerous_op(
    statements: Sequence[exp.Expression], dialect: str
) -> str | None:
    """Reject side-effecting / injection-shaped constructs that are not writes.

    Three surfaces, all AST-typed:

    - **Stacked statements** — more than one statement in a single candidate is
      the classic SQL-injection shape; a question maps to exactly one query.
    - **ATTACH / DETACH / PRAGMA** — data-boundary escapes and engine-state flips.
      *All* PRAGMA are rejected, not just writes: read- vs write-PRAGMA cannot be
      told apart reliably on the AST, and no PRAGMA is a valid query answer, so
      default-deny is both safer and simpler.
    - **Unmodeled commands** — anything sqlglot could only parse as a generic
      ``Command`` (``VACUUM``, ``SET``, …) is engine state we do not understand
      and will not run. (A write ``Command`` like ``REPLACE`` is already caught
      upstream by read-only.)
    """
    if len(statements) > 1:
        return (
            f"{len(statements)} statements in one candidate; "
            "stacked queries are not permitted"
        )
    for stmt in statements:
        if isinstance(stmt, _DANGEROUS_TYPES):
            return (
                f"{type(stmt).__name__.upper()} is a side-effecting meta-command; "
                "not permitted"
            )
        if isinstance(stmt, exp.Command):
            verb = stmt.name.upper() or "an unrecognized statement"
            return f"{verb} is an unsupported/side-effecting command; not permitted"
    return None


# Cost/complexity budget — **heuristic-first**, read straight off the AST. No
# EXPLAIN: BIRD is SQLite (no cost-bearing EXPLAIN) and BIRD drives the headline
# numbers; EXPLAIN-based cost is a Postgres-only enhancement for a later step.
#
# The join ceiling is *calibrated against the frozen BIRD slice gold*, which tops
# out at 2 joins — so 4 is comfortable headroom that only a pathological query
# trips, never a legitimate analytical one. Likewise the slice gold has zero
# unconstrained (no-ON/USING, no-WHERE) joins and zero unbounded ``SELECT *``, so
# those checks cannot false-reject a real answer.
MAX_JOINS: int = 4


def _is_unbounded_star_scan(select: exp.Select, statement: exp.Expression) -> bool:
    """A ``SELECT *`` that dumps a whole *base table*: star projection over a
    single table, with no WHERE filter and no LIMIT.

    Deliberately narrow, to avoid false-rejecting a bounded query (which, pre
    self-correction, would silently drop pass@1):

    - ``COUNT(*)`` does not count — its star is nested in the function, not a
      top-level projection.
    - a star over a **subquery / derived table** is excluded — the inner query may
      already be bounded (``SELECT * FROM (SELECT ... WHERE ...) z``).
    - a star with a **GROUP BY** is excluded — aggregation bounds the cardinality.
    - a star with a **join** is excluded — the join/cartesian checks own that shape.
    """
    has_star = any(isinstance(proj, exp.Star) for proj in select.expressions)
    if not has_star or select.args.get("joins") or select.args.get("group"):
        return False
    from_ = select.args.get("from_")
    source = from_.this if from_ is not None else None
    if not isinstance(source, exp.Table):
        return False
    no_where = select.args.get("where") is None
    no_limit = statement.args.get("limit") is None and select.args.get("limit") is None
    return no_where and no_limit


def _check_cost(statements: Sequence[exp.Expression], dialect: str) -> str | None:
    """Reject queries whose AST shape implies a runaway/abusive scan.

    Three heuristic signals, all structural:

    - **Cartesian product** — a join with no ``ON``/``USING`` predicate *and* no
      ``WHERE`` to constrain it (a true cross product). Old-style
      ``FROM a, b WHERE a.id = b.id`` joins keep their WHERE and are not flagged.
      A *present-but-non-joining* WHERE (``FROM a, b WHERE a.x > 0``) is a
      deliberate accepted gap: proving a WHERE actually correlates the tables is
      beyond a cheap deterministic AST check, and we favor not false-rejecting.
    - **Join explosion** — more joins than :data:`MAX_JOINS` (calibrated headroom
      over the BIRD gold).
    - **Unbounded ``SELECT *`` scan** — a star projection with neither WHERE nor
      LIMIT, i.e. a full-table dump.
    """
    for stmt in statements:
        for select in stmt.find_all(exp.Select):
            joins = select.args.get("joins") or []
            unconstrained = any(
                not j.args.get("on") and not j.args.get("using") for j in joins
            )
            if unconstrained and select.args.get("where") is None:
                return (
                    "join with no ON/USING predicate and no WHERE; "
                    "this is a cartesian product"
                )

        n_joins = len(list(stmt.find_all(exp.Join)))
        if n_joins > MAX_JOINS:
            return f"{n_joins} joins exceeds the complexity budget of {MAX_JOINS}"

        root = stmt if isinstance(stmt, exp.Select) else stmt.find(exp.Select)
        if root is not None and _is_unbounded_star_scan(root, stmt):
            return "SELECT * with no WHERE or LIMIT; this is an unbounded full scan"
    return None


# A guard rule: inspect the parsed statements (already split per ``;``) and the
# dialect, return a reject reason or ``None`` to pass. Rules are pure functions
# of the AST — the registry mirrors ``eval.compare``'s rule pipeline so checks
# slot in without touching the gate's control flow.
GuardRule = Callable[[Sequence[exp.Expression], str], str | None]

_RULES: dict[str, GuardRule] = {
    "read_only": _check_read_only,
    "dangerous_op": _check_dangerous_op,
    "cost": _check_cost,
}

# The checks run, in order, on every candidate; the first rule to fire wins
# (fail-fast). Read-only and dangerous-op are correctness/safety gates; cost is
# the heuristic complexity budget, last so a clearer rejection reason wins first.
DEFAULT_GUARD_RULES: tuple[str, ...] = ("read_only", "dangerous_op", "cost")


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
