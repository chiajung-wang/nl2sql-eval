"""Thin observability seam (instrument-as-you-build).

A stage-level logging hook added during Steps 1–7. Step 8 wires these seams to
Langfuse and enforces redacted logging. For now it emits structured logs only —
no Langfuse, no PII handling yet. Keep the seam thin: a logging interface, not an
integration.

Convention: each pipeline stage calls ``stage_span`` once it gains behavior
(Steps 2+). The stubs are docstring-only today, so nothing is wired yet — the
seam exists and is callable, and stages adopt it as they grow.

Contract: only redacted/safe fields may be attached via ``**fields`` or the
yielded dict. Raw PII must never flow through here — scoring happens upstream of
redaction, but logs only ever see the presented (redacted) result (CLAUDE.md §5).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("nl2sql")


def log_stage(stage: str, **fields: Any) -> None:
    """Emit a single structured stage event."""
    logger.info("%s", json.dumps({"stage": stage, **fields}, default=str))


@contextmanager
def stage_span(stage: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Wrap a pipeline stage, logging its start, end, and duration in ms.

    Yields a mutable dict the caller may attach result fields to; those are
    folded into the stage-end event.
    """
    extra: dict[str, Any] = {}
    start = time.perf_counter()
    log_stage(stage, event="start", **fields)
    try:
        yield extra
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        log_stage(stage, event="end", duration_ms=duration_ms, **extra)
