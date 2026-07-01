"""Sampled value index for literal→field matching (Step 12, #141).

Source: Shkapenyuk et al., arXiv:2505.19988v2 §3 — the literal-matching loop. A
recurring wrong-answer class is **right value, wrong column**: the generator
constrains a literal (``'Fresno County Office of Education'``) against a
plausible-but-wrong field. The paper handles it deterministically: index sampled
field values, then check whether each literal in the generated SQL actually occurs
in the field it is constrained against; if not, find which fields *do* contain it
and ask the model to rephrase. Their worked example flips a ``County Name``
constraint to the correct ``District`` field.

This module is the **index** half — deterministic, sampled, offline. It maps a
normalized value to the set of columns whose sample contains it, so a lookup answers
"which columns hold this literal?" mechanically (no LLM, no regex for SQL semantics
— that rule governs the *literal extraction*, which is sqlglot-AST, in
``pipeline/literal_check.py``). It is a **moderate sample, not the full column** —
the paper's explicit scalability caution — so a lookup can miss a value the column
really has (the *false-steer* risk the eval reports). PII columns (the db's
redaction policy) are **never indexed** — their values must not ride into a steering
prompt (CLAUDE.md §5.3), mirroring the profiler's shape-only rule (#140).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# A moderate per-column sample — enough to answer "does this column hold this
# categorical/name value?" for the low-cardinality columns literals bind to, while
# staying bounded on a wide table (the paper caps at ~10k; BIRD columns are smaller).
DEFAULT_VALUE_SAMPLE = 1000
# Skip values longer than this: a literal a question pins is a code/name/enum, not a
# free-text blob, so indexing long text is noise (and a cost).
MAX_VALUE_LEN = 120


def normalize_value(value: object) -> str:
    """Casefold + strip a value for case-insensitive, whitespace-robust matching.

    The one normalization applied on both sides — indexing a column's values and
    looking up a query literal — so ``'Fresno '`` and ``'fresno'`` match. Non-string
    values are stringified first (an id literal matches its stored form)."""
    return str(value).strip().casefold()


@dataclass(frozen=True)
class ValueIndex:
    """Normalized value → the set of ``"table.column"`` keys whose sample holds it.

    ``indexed_columns`` is the set of column keys that were sampled at all — so a
    lookup can tell "column not indexed" (unknown) from "column sampled, value
    absent" (a real off-column signal). Both keys are casefolded ``table.column``.
    """

    values: dict[str, frozenset[str]] = field(default_factory=dict)
    indexed_columns: frozenset[str] = frozenset()

    def columns_containing(self, value: object) -> frozenset[str]:
        """Column keys whose sample contains ``value`` (normalized); empty if none."""
        return self.values.get(normalize_value(value), frozenset())

    def is_indexed(self, column_key: str) -> bool:
        """Whether ``column_key`` (casefolded ``table.column``) was sampled at all."""
        return column_key.casefold() in self.indexed_columns

    def column_contains(self, column_key: str, value: object) -> bool:
        """Whether ``column_key``'s sample contains ``value`` (normalized)."""
        return column_key.casefold() in self.columns_containing(value)


def build_value_index(
    engine: Engine,
    *,
    sample: int = DEFAULT_VALUE_SAMPLE,
    redact_columns: frozenset[str] = frozenset(),
    max_value_len: int = MAX_VALUE_LEN,
) -> ValueIndex:
    """Build a sampled value index over ``engine``'s text-ish columns (read-only).

    For each column, pull up to ``sample`` distinct non-NULL values via a bounded
    ``SELECT DISTINCT … LIMIT`` (so a wide column stays cheap), keep the short ones,
    and map each normalized value to the columns that hold it. ``redact_columns``
    (casefolded ``table.column`` — the db's PII columns) are **skipped entirely**, so
    no PII value is ever indexed or surfaced in a steering prompt (§5.3). Any per-
    column read failure degrades to skipping that column, never raising.
    """
    inspector = inspect(engine)
    values: dict[str, set[str]] = {}
    indexed: set[str] = set()
    with engine.connect() as conn:
        for table in sorted(inspector.get_table_names()):
            for col in inspector.get_columns(table):
                column = col["name"]
                key = f"{table.casefold()}.{column.casefold()}"
                if key in redact_columns:
                    continue
                try:
                    rows = conn.execute(
                        text(
                            f'SELECT DISTINCT "{column}" FROM "{table}" '
                            f'WHERE "{column}" IS NOT NULL LIMIT :n'
                        ),
                        {"n": sample},
                    ).fetchall()
                except Exception:
                    continue
                indexed.add(key)
                for (value,) in rows:
                    text_value = str(value)
                    if len(text_value) > max_value_len:
                        continue
                    values.setdefault(normalize_value(text_value), set()).add(key)
    return ValueIndex(
        values={v: frozenset(cols) for v, cols in values.items()},
        indexed_columns=frozenset(indexed),
    )
