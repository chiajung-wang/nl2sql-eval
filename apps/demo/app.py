"""Streamlit shell over :func:`apps.demo.runner.run_demo` — reveal the wrapper.

Run it:

    uv sync --group demo
    uv run streamlit run apps/demo/app.py

This file is intentionally thin: all logic is in ``runner.py`` (tested). It wires
the chosen dataset to an engine + schema, calls the shared pipeline, and renders
the returned :class:`~apps.demo.runner.DemoView` — guardrail decision, retry
count, cost, terminal state, and the *presented (redacted)* result. It never
shows the raw verified rows the harness scores (CLAUDE.md §3/§5).

Datasets:
  - **payments** — the Postgres demo with PII columns (the redaction showcase);
    needs ``PAYMENTS_DB_URL`` + a seeded db (``docker compose up -d`` then
    ``uv run python -m eval.datasets.payments.load``).
  - **bird/<db>** — a BIRD SQLite db (no PII); needs the BIRD data downloaded.

A provider key (e.g. ``ANTHROPIC_API_KEY``) is required for the live model call.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from apps.demo.runner import DemoView, badge_for, parse_dataset, run_demo
from nl2sql.pipeline.redact import NO_REDACTION, RedactionPolicy

PAYMENTS_SCHEMA = (
    Path(__file__).resolve().parents[2] / "eval/datasets/payments/schema.sql"
)

# Generic badge severity → the Streamlit status widget that renders it.
_LEVEL_WIDGET = {"ok": "success", "warn": "warning", "error": "error", "info": "info"}


@st.cache_resource
def _payments_engine():
    from nl2sql.pipeline.execute import get_engine

    return get_engine()


@st.cache_resource
def _bird_engine(db_id: str):
    from eval.datasets.bird import loader

    return loader.get_engine(db_id)


def _load_dataset(choice: str) -> tuple[object, str, str, str, RedactionPolicy]:
    """Return ``(engine, schema, db_id, dialect, redaction_policy)`` for a choice.

    The choice → ``(kind, db_id, dialect)`` resolution is the pure, tested
    ``parse_dataset``; this shell only does the IO (build the engine, read the
    schema, derive the PII policy).
    """
    kind, db_id, dialect = parse_dataset(choice)
    if kind == "payments":
        schema = PAYMENTS_SCHEMA.read_text()
        return (
            _payments_engine(),
            schema,
            db_id,
            dialect,
            RedactionPolicy.from_ddl(schema),
        )
    from eval.datasets.bird import loader

    engine = _bird_engine(db_id)
    return engine, loader.schema_text(engine), db_id, dialect, NO_REDACTION


def _render(view: DemoView) -> None:
    emoji, level = badge_for(view.terminal_state)
    getattr(st, _LEVEL_WIDGET[level])(
        f"{emoji}  Terminal state: **{view.terminal_state}**"
    )

    cols = st.columns(4)
    cols[0].metric("Guardrail", "allowed" if view.guard_allowed else "rejected")
    cols[1].metric("Attempts", view.attempts)
    list_cost = (
        f"${view.list_cost_usd:.6f}" if view.list_cost_usd is not None else "n/a"
    )
    cols[2].metric("Cost (list)", list_cost)
    cols[3].metric("Tokens", f"{view.input_tokens}+{view.output_tokens}")

    if not view.guard_allowed:
        st.warning(
            f"🛡️ Guardrail **{view.guard_rule}** rejected the query pre-execution: "
            f"{view.guard_reason}"
        )

    st.subheader("Generated SQL")
    st.code(view.candidate_sql or "(no SQL produced)", language="sql")

    if view.error:
        st.subheader("Execution error")
        st.code(view.error)

    if view.presented_rows is not None:
        st.subheader("Presented result (redacted)")
        st.caption(
            "Post-redaction — the only result a user ever sees. PII columns are "
            "masked here; the harness scores the raw result upstream of this exit."
        )
        st.dataframe(
            {
                col: [row[i] for row in view.presented_rows]
                for i, col in enumerate(view.presented_columns or [])
            },
            use_container_width=True,
        )

    if view.provider_cost_usd is not None:
        st.caption(f"Provider-reported cost: ${view.provider_cost_usd:.6f}")


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="nl2sql-eval demo", page_icon="🔍", layout="wide")
    st.title("🔍 nl2sql-eval — reveal the wrapper")
    st.caption(
        "The same pipeline the harness measures, run live. This surfaces the "
        "machinery — guardrail decision, retry count, cost, terminal state — not a "
        "chatbot."
    )

    with st.sidebar:
        st.header("Configuration")
        dataset = st.text_input(
            "Dataset", value="payments", help="`payments` or `bird/<db_id>`"
        )
        model = st.text_input("Model", value="anthropic/claude-sonnet-4-6")
        max_attempts = st.slider(
            "Retry budget (k)",
            1,
            5,
            1,
            help="1 = single-shot (pass@1); >1 arms the loop",
        )

    question = st.text_area(
        "Question",
        value="How many users are based in the US?",
        help="A natural-language question against the selected database.",
    )

    if st.button("Run", type="primary"):
        try:
            engine, schema, db_id, dialect, policy = _load_dataset(dataset)
        except Exception as exc:  # dataset/engine wiring failed — surface it plainly
            st.error(f"Could not load dataset `{dataset}`: {exc}")
            return
        with st.spinner("Running the pipeline…"):
            view = run_demo(
                question,
                engine=engine,
                schema=schema,
                db_id=db_id,
                dialect=dialect,
                model=model,
                redaction_policy=policy,
                max_attempts=max_attempts,
            )
        _render(view)


if __name__ == "__main__":
    main()
