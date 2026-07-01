"""Candidate diversity levers for majority voting (Step 12, #142).

The paper introduces candidate diversity two ways: (a) varying the LLM seed and
(b) **randomizing the order of the schema-linked fields** in the prompt. Lever (a)
only has an effect with a *stochastic* live model, so it is exercised in the
deferred live run (a seed threaded to the provider); lever (b) is **deterministic
and offline-testable** and lives here: a seeded permutation of each table's columns,
so candidate *i* sees the same tables and values in a different field order.

This is a harness-side generation lever (it composes a schema variant per candidate),
so it lives in ``eval/`` alongside the voting it feeds — the pipeline itself is
untouched and never imports it. Reordering columns cannot change a query's *meaning*,
only the prompt the generator reads, so the executed result-set (and thus what the
harness scores) is unaffected by the shuffle itself — only by whichever candidate the
vote then selects.
"""

from __future__ import annotations

from random import Random

from nl2sql.schema_index import SchemaIndex, TableMeta


def shuffle_field_order(index: SchemaIndex, seed: int) -> SchemaIndex:
    """A copy of ``index`` with each table's columns permuted by ``seed``.

    Deterministic in ``seed`` (a seeded :class:`random.Random`), so candidate *i* is
    reproducible (§9). Table order and every table's columns/FKs/description are
    preserved — only the *column order within each table* changes, which is the
    field-order diversity the prompt renders. ``seed=0`` conventionally means "no
    shuffle" (the identity), so candidate 0 is the unshuffled baseline.
    """
    if seed == 0:
        return index
    rng = Random(seed)
    tables = []
    for table in index.tables:
        cols = list(table.columns)
        rng.shuffle(cols)
        tables.append(
            TableMeta(
                name=table.name,
                columns=tuple(cols),
                foreign_keys=table.foreign_keys,
                description=table.description,
            )
        )
    return SchemaIndex(tuple(tables))
