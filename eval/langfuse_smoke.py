"""Langfuse smoke check: prove a live trace lands, end to end.

Run this once after putting Langfuse keys in ``.env`` to confirm the wiring is
actually exporting — it exercises the *real* ``nl2sql.obs`` seam (the same
``trace_attributes`` + ``stage_span`` the pipeline uses), not a bespoke call, so a
green run here means the pipeline's traces will appear too.

    uv run python -m eval.langfuse_smoke

It is offline-safe: with no keys set it reports that tracing is disabled and exits
non-zero (nothing is sent). With keys set it validates credentials/host via
``auth_check``, emits one tiny ``langfuse-smoke`` trace (a ``pipeline`` root with a
nested ``generation`` — only safe shapes/counts, never PII), flushes, and prints
the trace URL to open in the UI.
"""

from __future__ import annotations

from dotenv import load_dotenv

from nl2sql import obs


def main() -> int:
    load_dotenv()

    # Re-read the environment now that .env is loaded, then resolve the client.
    obs.reset_client()
    client = obs.get_client()
    if client is None:
        print(
            "Langfuse tracing is DISABLED — set LANGFUSE_PUBLIC_KEY and "
            "LANGFUSE_SECRET_KEY (and LANGFUSE_HOST / LANGFUSE_BASE_URL) in .env.\n"
            "Nothing was sent; the pipeline runs as pure structured logging."
        )
        return 1

    # Fail fast and clearly on bad creds or wrong region, instead of a silent drop.
    try:
        if not client.auth_check():
            print(
                "Langfuse auth_check FAILED — keys or host are wrong for this "
                "project/region. Check LANGFUSE_HOST matches the key's region."
            )
            return 1
    except Exception as exc:  # network/host errors surface here, not as a drop
        print(f"Langfuse auth_check errored: {type(exc).__name__}: {exc}")
        return 1

    # Emit one trace through the real seam — same shape a pipeline run produces.
    trace_url: str | None = None
    with (
        obs.trace_attributes(trace_name="langfuse-smoke", tags=["smoke", "db:_smoke"]),
        obs.stage_span(
            "pipeline",
            trace_input="smoke: is tracing live?",
            db_id="_smoke",
            model="smoke-model",
        ) as extra,
    ):
        with obs.stage_span(
            "generate", as_type="generation", db_id="_smoke", model="smoke-model"
        ) as gen:
            gen["candidate_sql"] = "SELECT 1"
            gen["input_tokens"] = 1
            gen["output_tokens"] = 1
        extra["presented_row_count"] = 1
        extra["presented_column_count"] = 1
        trace_id = client.get_current_trace_id()
        trace_url = client.get_trace_url(trace_id=trace_id)

    obs.flush()  # short-lived script: export before exit (atexit also flushes)
    print("Langfuse smoke trace sent ✓")
    print(f"  open: {trace_url or '(trace id unavailable; check the Traces view)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
