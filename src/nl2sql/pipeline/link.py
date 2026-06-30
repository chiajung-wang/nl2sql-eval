"""Schema linking by task-alignment (Step 12, #138).

Source: Shkapenyuk et al., "Automatic Metadata Extraction for Text-to-SQL"
(arXiv:2505.19988v2, §3 — the AT&T #1 BIRD submission). Their contrarian finding,
which this module implements: LLMs are **poor at directly naming relevant
tables/columns** (a task they were not trained on) but **good at generating SQL**.
So rather than ask the model "which tables are relevant?", we ask it to *generate
SQL* across a few schema variants and **harvest the tables the generated SQL
actually references** — the union is the linked schema. Recall over precision:
"better too many fields than too few" (paper §3), bounded by the variants.

This is the alternative initial-retrieval strategy to the lexical schema-RAG in
``retrieve.py`` — the open *method* for Step-11 #135's table-selection frontier.
It is scored on the same apparatus: ``state.retrieved_tables`` feeds the harness's
retrieval-recall metric (PRD rule 7), so the linker's coverage is measured against
the gold query's tables exactly as RAG's is.

**Determinism boundary (CLAUDE.md §4).** The *harvesting* is pure sqlglot-AST table
extraction — no regex for SQL semantics, no LLM in the parse. The LLM is used only
to produce the candidate SQL whose tables we read (the ``generate_sql`` callable,
injected by the caller), so this module is import-shared and trivially testable
with a fake generator. It calls nothing from ``eval/``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from nl2sql.schema_index import DEFAULT_MAX_TABLES, SchemaIndex

# BIRD is SQLite; fall back to the generic parser so table extraction is
# dialect-robust (mirrors the comparator's and recall metric's tolerant parse).
LINK_DIALECTS: tuple[str | None, ...] = ("sqlite", None)

# The schema variants the linker generates against. Two by default — the paper
# uses focused-vs-full schema (and, with #140, profile variants): a *focused*
# (lexical-RAG) schema biases toward precision, the *full* schema toward recall;
# unioning their harvested tables is the recall-over-precision move. Profile
# variants ("minimal"/"maximal") slot in once #140's profiling metadata lands.
DEFAULT_LINK_VARIANTS: tuple[str, ...] = ("focused", "full")


def tables_in_sql(
    sql: str, *, dialects: Sequence[str | None] = LINK_DIALECTS
) -> set[str]:
    """Base table names a query references, casefolded, from the AST.

    The canonical "tables in a SQL string" extractor, shared by the linker (to
    harvest a candidate's tables) and the retrieval-recall metric (to read the
    gold query's tables) — one definition, no fork (the issue's reuse rule).

    Deterministic — sqlglot ``exp.Table`` nodes, never a string scan (CLAUDE.md
    §4): an alias, a column named like a table, or the word ``from`` in a string
    literal can't fool it. **CTE names are excluded**: a reference to a ``WITH``
    block parses as a ``Table`` too, but a retriever (which selects real schema
    tables) can never surface a CTE, so counting it would distort coverage — and a
    CTE shadowing a real table name would falsely credit it. Returns an empty set
    when ``sql`` parses under no known dialect (the candidate is then unusable for
    linking — the caller degrades), so a malformed generation never raises here.
    """
    for dialect in dialects:
        try:
            tree = sqlglot.parse_one(sql, dialect=dialect)
        except ParseError:
            continue
        if tree is None:
            continue
        tables = {t.name.casefold() for t in tree.find_all(exp.Table) if t.name}
        cte_names = {
            c.alias_or_name.casefold()
            for c in tree.find_all(exp.CTE)
            if c.alias_or_name
        }
        return tables - cte_names
    return set()


def _variant_tables(
    index: SchemaIndex, question: str, variant: str, *, max_tables: int
) -> list[str]:
    """The table set defining one schema variant the linker generates against."""
    if variant == "full":
        return [t.name for t in index.tables]
    if variant == "focused":
        return index.relevant_tables(question, max_tables=max_tables)
    raise ValueError(f"unknown schema-link variant: {variant!r}")


def link_tables(
    question: str,
    index: SchemaIndex,
    generate_sql: Callable[[str], str],
    *,
    max_tables: int = DEFAULT_MAX_TABLES,
    variants: Sequence[str] = DEFAULT_LINK_VARIANTS,
) -> list[str]:
    """Link a question to schema tables by harvesting generated SQL (task-alignment).

    For each schema ``variant``, render that variant's schema, ask ``generate_sql``
    for candidate SQL against it, and harvest the **real** tables that SQL
    references (a hallucinated name the schema doesn't contain is dropped — it
    can't be "retrieved"). The **union** across variants is the linked set, returned
    in the index's declaration order (the canonical render order, so only *which*
    tables differ between strategies, never the rendering).

    ``generate_sql`` is injected — the caller wires it to the real LLM client
    (graph node) or a fake (tests). A variant whose generation raises or yields no
    in-schema table simply contributes nothing; if **no** variant yields any
    in-schema table, the linker degrades to the lexical-RAG focused set so the
    generator is never handed an empty schema (mirrors ``relevant_tables``'
    full-dump fallback — degrade, never starve).
    """
    valid = {t.name.casefold(): t.name for t in index.tables}
    harvested: set[str] = set()
    for variant in variants:
        schema = index.render(
            _variant_tables(index, question, variant, max_tables=max_tables)
        )
        try:
            sql = generate_sql(schema)
        except Exception:
            # A linking generation that fails (network, provider) is non-fatal —
            # the other variants still contribute; only an all-empty harvest degrades.
            continue
        for name in tables_in_sql(sql):
            real = valid.get(name)
            if real is not None:
                harvested.add(real)
    if not harvested:
        return index.relevant_tables(question, max_tables=max_tables)
    order = {t.name: i for i, t in enumerate(index.tables)}
    return sorted(harvested, key=lambda n: order[n])
