"""Stage: redact — column-aware PII masking, the *presented* pipeline exit.

Deterministic and schema-driven. The pipeline has **two exits** (CLAUDE.md §3):

- the **raw verified result** (``state.result_rows``/``result_columns``) — what
  the harness scores against gold, **upstream of redaction**;
- the **presented result** (``state.presented_rows``/``presented_columns``) —
  post-redaction, the *only* result the demo shows a user or that anything writes
  to logs/traces.

This stage produces the second from the first **without ever touching the first**,
so redaction can never corrupt scoring (CLAUDE.md §5.2): the harness keeps scoring
the pristine raw rows. Masking is *column-aware* (it blanks the values of columns
the schema marks as PII) and *schema-driven* (the PII column set comes from the
schema's own ``-- PII`` annotations, not a guess) and *deterministic* (a fixed
mask string, no LLM, no value-sniffing regex). The redacted **column names** are
schema metadata, not data, so they are safe to surface on the span; the masked
**values** are what must never leak.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState

# The fixed mask written over a PII value. A constant, not derived from the value,
# so nothing about the original (length, prefix, format) survives redaction.
MASK = "‹redacted›"

# A column is PII iff its DDL line carries a ``-- PII`` marker. ``\bPII\b`` matches
# ``-- PII`` and ``-- PII (cardholder data)`` but the ``(?!-)`` lookahead excludes
# ``PII-adjacent`` (the schema's deliberately weaker label for e.g. card brand) —
# only columns the schema calls PII outright are masked.
_PII_MARKER = re.compile(r"(?i)\bPII\b(?!-)")


def _norm(name: str) -> str:
    """Canonical column key: lowercased, stripped — so ``Email`` matches ``email``."""
    return name.strip().strip('"').lower()


@dataclass(frozen=True)
class RedactionPolicy:
    """The set of PII column names to mask, derived from a schema (schema-driven).

    Column-name based on purpose: it is the deterministic, portable signal the
    schema actually carries. A result column is masked when its (normalized) name
    is in :attr:`pii_columns` — so ``SELECT email FROM users`` and
    ``SELECT u.email FROM users u`` both redact, regardless of table aliasing.

    **Known limitation (deliberate, tested):** matching is on the *output* column
    name, so a PII column **aliased to a non-PII name** — ``SELECT email AS
    contact`` — escapes masking. Closing that needs sqlglot projection resolution
    (output column → base column, through aliases / ``SELECT *`` / expressions),
    which is deeper than this stage and would belong with the trace-debugging work.
    The conservative, honest position for now: name-based masking catches the
    direct and table-qualified cases; the alias escape is pinned by a test
    (``test_redact_aliased_pii_is_a_known_limitation``) so the trade-off is a
    conscious one, not a silent hole.
    """

    pii_columns: frozenset[str]

    @classmethod
    def from_ddl(cls, ddl: str) -> RedactionPolicy:
        """Parse a column's ``-- PII`` annotations out of ``CREATE TABLE`` DDL.

        Each column line is ``<name> <type> … [-- comment]``; a line whose comment
        is marked PII contributes its first token (the column name) to the policy.
        Reading the schema's own labels keeps the policy *schema-driven* — add a
        ``-- PII`` marker in the DDL and that column is redacted, no code change.
        """
        pii: set[str] = set()
        for raw_line in ddl.splitlines():
            code, sep, comment = raw_line.partition("--")
            if not sep or not _PII_MARKER.search(comment):
                continue
            tokens = code.split()
            if tokens:
                pii.add(_norm(tokens[0]))
        return cls(frozenset(pii))

    def pii_indices(self, columns: list[str]) -> list[int]:
        """Positions in ``columns`` whose name the policy marks as PII."""
        return [i for i, c in enumerate(columns) if _norm(c) in self.pii_columns]


# An empty policy: redaction still runs (the presented exit is always populated on
# a successful run) but masks nothing — the BIRD benchmark path, which carries no
# PII annotations, and the default when no schema policy is supplied.
NO_REDACTION = RedactionPolicy(frozenset())


def redact(state: RunState, policy: RedactionPolicy = NO_REDACTION) -> RunState:
    """Produce the presented (redacted) result from the raw verified result.

    Copies the raw rows into the presented exit, blanking every PII column's value
    with :data:`MASK`. The raw ``result_rows``/``result_columns`` are left exactly
    as ``execute`` produced them, so the harness still scores the unredacted truth
    (CLAUDE.md §5.2). A run that errored or was guard-rejected has no result to
    present, so the presented exit stays ``None``. Mutates and returns ``state``.

    The span records only counts and the **names** of the redacted columns (schema
    metadata, never a value) — so even the observability of redaction leaks nothing.
    """
    with stage_span("redact", db_id=state.db_id) as extra:
        if state.result_rows is None:
            extra["presented"] = False
            return state

        columns = list(state.result_columns or [])
        pii_idx = policy.pii_indices(columns)
        if pii_idx:
            idx = set(pii_idx)
            presented_rows = [
                tuple(
                    MASK if i in idx and v is not None else v for i, v in enumerate(row)
                )
                for row in state.result_rows
            ]
        else:
            presented_rows = [tuple(row) for row in state.result_rows]

        state.presented_columns = columns
        state.presented_rows = presented_rows

        extra["row_count"] = len(presented_rows)
        extra["redacted_columns"] = [columns[i] for i in pii_idx]
    return state
