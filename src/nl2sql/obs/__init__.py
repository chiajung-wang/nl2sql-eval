"""Observability seam — structured logs + Langfuse spans (instrument-as-you-build).

A stage-level hook added during Steps 1–7 as a *thin* logging interface. Step 8
(this issue) wires those same seams to **Langfuse**: each ``stage_span`` now also
opens a Langfuse observation, so one pipeline run becomes one trace whose child
spans mirror the stages (``retrieve → generate → guard → execute → correct``;
``redact`` joins in the next issue). Nesting is automatic — the root ``pipeline``
span opens the trace and every stage span entered inside it becomes a child via
the Langfuse (OpenTelemetry) context.

The wiring is **offline-safe by construction**. ``get_client`` returns a live
Langfuse client only when ``LANGFUSE_PUBLIC_KEY`` *and* ``LANGFUSE_SECRET_KEY``
are set; otherwise it returns ``None`` and ``stage_span`` degrades to exactly the
prior structured-logging behavior — no network, no keys, nothing to mock. Live
trace capture is therefore deferred until a key is supplied; the seam is proven
offline (the tests inject a fake recorder, never a real client).

Contract: only redacted/safe fields may be attached via ``**fields`` or the
yielded ``extra`` dict — both flow to the span. Raw PII must never flow through
here: scoring happens upstream of redaction, but logs and traces only ever see
the presented (redacted) result (CLAUDE.md §5). The stages uphold this by
attaching shapes and counts (row/column counts, the generated SQL, the guard
verdict, token/cost numbers) — never result rows.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

logger = logging.getLogger("nl2sql")

# Sentinel for "client not yet resolved" vs the resolved-but-absent ``None``.
_UNSET: Any = object()
_CLIENT: Any = _UNSET


def get_client() -> Any | None:
    """Return the process-wide Langfuse client, or ``None`` when unconfigured.

    A live client is built lazily on first use and only when both Langfuse keys
    are present in the environment — so an offline run (the default, and every
    test) skips span creation entirely and ``stage_span`` is pure structured
    logging. The result is cached; ``set_client``/``reset_client`` are the test
    seams that swap in a fake recorder or clear the cache.
    """
    global _CLIENT
    if _CLIENT is _UNSET:
        _CLIENT = _build_client()
    return _CLIENT


def set_client(client: Any | None) -> None:
    """Inject a client (a fake recorder in tests; ``None`` to force the no-op path)."""
    global _CLIENT
    _CLIENT = client


def reset_client() -> None:
    """Drop the cached client so the next ``get_client`` re-reads the environment."""
    global _CLIENT
    _CLIENT = _UNSET


def _build_client() -> Any | None:
    """Construct a Langfuse client from the environment, or ``None`` if unconfigured.

    Both keys are required; their absence is the *normal* offline case, not an
    error. Any import/construction failure also degrades to ``None`` so a missing
    or misconfigured Langfuse never breaks the pipeline — observability is a seam,
    never a dependency of correctness.
    """
    if not (
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    ):
        return None
    # The Python SDK reads ``LANGFUSE_HOST``; the ``langfuse-cli`` reads
    # ``LANGFUSE_BASE_URL``. Honor either so one env var drives both and a non-EU
    # region (e.g. ``https://jp.cloud.langfuse.com``) isn't silently ignored —
    # without this, keys for another region default to EU cloud and fail to auth.
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL")
    try:
        from langfuse import Langfuse

        # Keys come from the environment; ``host`` is passed explicitly so the
        # BASE_URL fallback above is honored (Langfuse() alone reads only HOST).
        return Langfuse(host=host) if host else Langfuse()
    except Exception:  # pragma: no cover - defensive; obs must never break a run
        logger.warning("langfuse client unavailable; tracing disabled", exc_info=True)
        return None


def flush() -> None:
    """Flush buffered spans to Langfuse (Langfuse batches in the background).

    A no-op offline. Entrypoints (the harness, the demo) may call this at the end
    of a run so a short-lived process exports before exit; ``atexit`` also flushes.
    """
    client = get_client()
    if client is not None:
        client.flush()


def log_stage(stage: str, **fields: Any) -> None:
    """Emit a single structured stage event."""
    logger.info("%s", json.dumps({"stage": stage, **fields}, default=str))


# Result key that maps to Langfuse's native cost axis (tokens map to
# ``usage_details``), captured on the span instead of generic metadata so the
# trace surfaces it on its own axis — this is what feeds the pass@1-vs-pass@k
# cost analysis.
_COST_KEY = "cost_usd"


def _span_update(
    span: Any,
    as_type: str,
    fields: dict[str, Any],
    extra: dict[str, Any],
    duration_ms: float,
    error: BaseException | None = None,
) -> None:
    """Fold a finished stage's safe fields into its Langfuse observation.

    Counts/SQL/verdict ride in ``output`` + ``metadata``; tokens and cost are
    promoted to Langfuse's native ``usage_details``/``cost_details`` so the trace
    aggregates them. A ``generation`` also records the model. A stage whose body
    *raised* is marked ``level="ERROR"`` with the exception class as the status
    message, so a failing question's trace shows *which* span failed — the Step 8
    "diagnosable from its trace" goal. (The exception *type*, never its message:
    a message can echo query text; the class name cannot leak PII.) Best-effort: a
    Langfuse hiccup must never surface as a pipeline failure.
    """
    metadata = {"duration_ms": duration_ms}
    update: dict[str, Any] = {"output": extra, "metadata": metadata}

    usage = {
        "input": extra["input_tokens"] if "input_tokens" in extra else None,
        "output": extra["output_tokens"] if "output_tokens" in extra else None,
    }
    usage = {k: v for k, v in usage.items() if v is not None}
    if usage:
        update["usage_details"] = usage
    if extra.get(_COST_KEY) is not None:
        update["cost_details"] = {"total": extra[_COST_KEY]}
    if as_type == "generation" and fields.get("model"):
        update["model"] = fields["model"]
    if error is not None:
        update["level"] = "ERROR"
        update["status_message"] = type(error).__name__

    try:
        span.update(**update)
    except Exception:  # pragma: no cover - obs must never break a run
        logger.warning("langfuse span update failed", exc_info=True)


@contextmanager
def trace_attributes(
    *,
    trace_name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> Iterator[None]:
    """Apply trace-level correlating attributes to every span opened inside.

    The Langfuse v4 seam for trace-level identity and filtering: ``trace_name``,
    ``session_id``, ``user_id``, ``tags`` and ``metadata`` are propagated (via
    ``propagate_attributes``) onto the root observation and *all* its children, so
    one run's trace is findable and filterable in the UI — name it, tag it with the
    db/model, and (when a caller threads one) group a whole eval batch under a
    single ``session_id`` in the Sessions view.

    Only safe, low-cardinality identifiers belong here — the db id, the model, a
    run id. **Never PII** (CLAUDE.md §5.3): result rows are masked by ``redact`` and
    never flow through here. Offline-safe and best-effort by construction: a no-op
    when Langfuse is unconfigured, and any failure degrades to a plain pass-through
    so observability is never a dependency of a run.
    """
    kwargs = {
        k: v
        for k, v in (
            ("trace_name", trace_name),
            ("session_id", session_id),
            ("user_id", user_id),
            ("tags", tags),
            ("metadata", metadata),
        )
        if v is not None
    }
    if get_client() is None or not kwargs:
        yield
        return

    cm: Any = None
    try:
        from langfuse import propagate_attributes

        cm = propagate_attributes(**kwargs)
        cm.__enter__()
    except Exception:  # pragma: no cover - obs must never break a run
        logger.warning("langfuse trace attributes unavailable", exc_info=True)
        cm = None
    try:
        yield
    finally:
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover - obs must never break a run
                logger.warning("langfuse trace attributes exit failed", exc_info=True)


@contextmanager
def stage_span(
    stage: str, *, as_type: str = "span", trace_input: Any = None, **fields: Any
) -> Iterator[dict[str, Any]]:
    """Wrap a pipeline stage: structured start/end logs *and* a Langfuse span.

    Logs the stage's start, end, and duration in ms (unchanged behavior), and —
    when Langfuse is configured — opens a child observation named ``stage`` under
    the current trace. Yields a mutable ``extra`` dict the caller attaches result
    fields to; on exit those fold into both the stage-end log event and the span
    (with tokens/cost promoted to Langfuse's native axes). ``as_type="generation"``
    marks an LLM call so token/cost usage attributes to a generation span and the
    model is recorded — the ``generate`` stage opts in.

    ``trace_input`` sets the observation's *input*. On the **root** span of a run
    (the ``pipeline`` span) this becomes the trace's input — the NL question (the
    user's own message, not result data), making the trace readable at a glance:
    question in, result-shape out. Only the safe NL question and result *shapes*
    are ever attached — raw PII never reaches the span (CLAUDE.md §5.3).

    If the wrapped body raises, the exception propagates unchanged (the stage's
    own error handling is untouched) but the span is first marked errored and the
    stage-end log records the exception class — so a failing run stays diagnosable
    on the trace. The span is best-effort and strictly additive: if Langfuse is
    absent or errors, this is exactly the prior log-only seam.
    """
    extra: dict[str, Any] = {}
    start = time.perf_counter()
    log_stage(stage, event="start", **fields)

    client = get_client()
    if client is not None:
        obs_kwargs: dict[str, Any] = {
            "name": stage,
            "as_type": as_type,
            "metadata": dict(fields),
        }
        if trace_input is not None:
            obs_kwargs["input"] = trace_input
        span_cm = client.start_as_current_observation(**obs_kwargs)
    else:
        span_cm = nullcontext(None)

    with span_cm as span:
        error: BaseException | None = None
        try:
            yield extra
        except BaseException as exc:
            error = exc
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 3)
            if span is not None:
                _span_update(span, as_type, fields, extra, duration_ms, error=error)
            end_fields = dict(extra)
            if error is not None:
                end_fields.setdefault("error", type(error).__name__)
            log_stage(stage, event="end", duration_ms=duration_ms, **end_fields)
