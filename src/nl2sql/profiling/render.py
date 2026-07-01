"""Mechanical profile→English rendering (Step 12, #140).

The deterministic middle step of the paper's pipeline (arXiv:2505.19988v2 §2.1):
turn a :class:`~nl2sql.profiling.profiler.ColumnProfile`'s statistics into plain
English **facts** — no LLM, no interpretation. This English is the context handed
to the (offline, cached) LLM summarizer; keeping it mechanical means the summarizer
input is reproducible and the whole rendering is unit-testable without a model.

The renderer *states* what the data shows ("14 characters, all digits, every value
distinct"); it never *concludes* what it means ("a school id") — that is the
summarizer's job, downstream. So this module has no opinions and no I/O.
"""

from __future__ import annotations

from nl2sql.profiling.profiler import CharClass, ColumnProfile, TableProfile

# Cap how many top values the English lists, so a rendering stays short even when a
# column is profiled with a larger ``top_k`` for the value index (#141).
_MAX_LISTED_VALUES = 5

_CHAR_CLASS_PHRASE: dict[CharClass, str] = {
    CharClass.DIGITS: "all digits",
    CharClass.ALPHA: "all letters",
    CharClass.ALNUM: "alphanumeric",
    CharClass.MIXED: "mixed characters",
}


def render_column_english(profile: ColumnProfile) -> str:
    """A one-paragraph English rendering of a column profile — deterministic facts.

    Ordered from identity (name, type) through completeness (nulls), cardinality
    (distinct / uniqueness), value shape (length, character class, common prefix,
    extremes), to the top values. Each clause is emitted only when the profile
    carries the signal, so a sparse column renders a short, honest description.
    """
    p = profile
    parts: list[str] = [f'Column "{p.name}" (declared type {p.declared_type or "?"}).']

    if p.row_count == 0:
        parts.append("The table is empty.")
        return " ".join(parts)

    if p.non_null_count == 0:
        parts.append(f"All {p.row_count} rows are NULL.")
        return " ".join(parts)

    # Completeness.
    if p.null_count == 0:
        parts.append(f"No NULLs across {p.row_count} rows.")
    else:
        pct = round(p.null_fraction * 100)
        parts.append(f"{p.null_count} of {p.row_count} rows are NULL ({pct}%).")

    # Cardinality / uniqueness.
    if p.is_unique:
        parts.append(f"All {p.distinct_count} non-NULL values are distinct (unique).")
    else:
        parts.append(f"{p.distinct_count} distinct values.")

    # Value shape. Each fragment reads as a predicate after "Values are …".
    shape: list[str] = []
    if p.is_constant_length and p.min_len is not None:
        shape.append(f"exactly {p.min_len} characters long")
    elif p.min_len is not None and p.max_len is not None:
        shape.append(f"{p.min_len}–{p.max_len} characters long")
    phrase = _CHAR_CLASS_PHRASE.get(p.char_class)
    if phrase is not None:
        shape.append(phrase)
    if p.common_prefix:
        shape.append(f'always beginning with "{p.common_prefix}"')
    if shape:
        parts.append("Values are " + ", ".join(shape) + ".")

    if p.min_value is not None and p.max_value is not None:
        if p.min_value == p.max_value:
            parts.append(f'The only value is "{p.min_value}".')
        else:
            parts.append(f'Ranges from "{p.min_value}" to "{p.max_value}".')

    # Top values (the enum / skew signal).
    if p.top_values and not p.is_unique:
        listed = p.top_values[:_MAX_LISTED_VALUES]
        rendered = ", ".join(f'"{v}" ({n})' for v, n in listed)
        more = "" if len(p.top_values) <= _MAX_LISTED_VALUES else ", …"
        parts.append(f"Most common: {rendered}{more}.")

    return " ".join(parts)


def render_table_english(profile: TableProfile) -> str:
    """Render a table's profile: a header line plus one line per column."""
    header = f'Table "{profile.name}" ({profile.row_count} rows):'
    lines = [f"- {render_column_english(c)}" for c in profile.columns]
    return "\n".join([header, *lines])
