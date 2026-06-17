"""Step 8 Definition-of-Done proof: a failing question, diagnosable from its trace.

Offline and deterministic — no live model, no Langfuse keys (the defer-API-key
discipline). A fake LLM client drives a **retry-exhausted** failure through the
**import-shared** pipeline (``graph.run_pipeline`` — the same loop the harness and
demo run) while an in-process :class:`TraceRecorder` captures the per-stage spans
*exactly* as Langfuse would: ``start_as_current_observation`` with automatic
parent/child nesting, ``update`` carrying each stage's safe output. The harness
classifies the terminal state.

The captured trace is printed and rendered to a self-contained HTML artifact for
the blog — proving the Step-8 "done when": you can open a failing question's
trace and see, per span, what each stage did (retrieved tables, generated SQL,
guard verdict, attempts, the execution error, the terminal state) — and that **no
raw PII appears anywhere** on it.

    uv run python -m eval.prove_step8     # prints the trace, writes example-trace.html

This is the offline proof and the blog visual; a live Langfuse trace is the same
shape once a key is supplied (``LANGFUSE_PUBLIC_KEY``/``LANGFUSE_SECRET_KEY``).
"""

from __future__ import annotations

import html
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from eval.harness import classify_terminal_state
from nl2sql import obs
from nl2sql.llm import LLMResponse
from nl2sql.pipeline.graph import run_pipeline
from nl2sql.pipeline.redact import RedactionPolicy
from nl2sql.pipeline.state import RunState, TerminalState

ARTIFACT = Path(__file__).resolve().parents[1] / "docs/plans/step-8/example-trace.html"

# A two-table schema with a natural PII surface (so the redact span is exercised
# and the no-PII guarantee has something to protect). The ``-- PII`` markers drive
# the redaction policy, exactly as the payments schema does.
DDL = """
CREATE TABLE users (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL,   -- PII
    full_name   TEXT NOT NULL,   -- PII
    country     TEXT NOT NULL
);
CREATE TABLE orders (
    id       INTEGER PRIMARY KEY,
    user_id  INTEGER NOT NULL REFERENCES users (id),
    amount   INTEGER NOT NULL
);
"""

QUESTION = "How many orders has each user placed?"

# A column the generator keeps referencing that does not exist — so the SQL parses
# (the guard allows it: read-only, in-scope) but every execution errors, and the
# capped retry budget is spent: the terminal state is RETRY_EXHAUSTED. A realistic
# failing question to debug from its trace.
BAD_SQL = "SELECT user_id, COUNT(missing_col) FROM orders GROUP BY user_id"


class _AlwaysWrongClient:
    """An ``nl2sql.llm`` stand-in that always returns the same broken SQL."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=BAD_SQL, input_tokens=12, output_tokens=8)


# --- the recorder: a Langfuse-shaped, in-process span tree -------------------


@dataclass
class Span:
    """One recorded observation — the same fields a Langfuse span carries."""

    name: str
    as_type: str
    metadata: dict[str, Any]
    output: dict[str, Any] | None = None
    duration_ms: float | None = None
    level: str | None = None
    status_message: str | None = None
    usage: dict[str, Any] | None = None
    children: list[Span] = field(default_factory=list)

    def walk(self) -> list[Span]:
        out = [self]
        for c in self.children:
            out.extend(c.walk())
        return out


class _RecordingSpan:
    """Wraps a :class:`Span`, absorbing ``update`` calls from ``stage_span``."""

    def __init__(self, span: Span) -> None:
        self._span = span

    def update(self, **kwargs: Any) -> None:
        self._span.output = kwargs.get("output")
        self._span.duration_ms = (kwargs.get("metadata") or {}).get("duration_ms")
        self._span.level = kwargs.get("level")
        self._span.status_message = kwargs.get("status_message")
        self._span.usage = kwargs.get("usage_details")


class TraceRecorder:
    """A drop-in for the Langfuse client: records the span tree for one run.

    Mirrors ``start_as_current_observation`` and its automatic nesting (children
    parent to the span open on the stack) so the recorded tree is the trace
    Langfuse would build — captured offline, no keys, no network.
    """

    def __init__(self) -> None:
        self.root: Span | None = None
        self._stack: list[Span] = []

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ):
        span = Span(name, as_type, dict(metadata or {}))
        if self._stack:
            self._stack[-1].children.append(span)
        else:
            self.root = span
        self._stack.append(span)
        try:
            yield _RecordingSpan(span)
        finally:
            self._stack.pop()

    def flush(self) -> None:  # parity with the real client; nothing to flush
        pass


@dataclass(frozen=True)
class CapturedTrace:
    """The captured failing run: its span tree, final state, and terminal bucket."""

    root: Span
    state: RunState
    terminal: TerminalState


def _build_engine() -> Engine:
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        for stmt in filter(None, (s.strip() for s in DDL.split(";"))):
            conn.execute(text(stmt))
        # Real PII the trace must never leak (the run errors, so it is never even
        # selected — the guarantee holds defensively regardless).
        conn.execute(
            text(
                "INSERT INTO users VALUES "
                "(1, 'alice@secret.example', 'Alice Lee', 'US')"
            )
        )
        conn.execute(text("INSERT INTO orders VALUES (1, 1, 4200)"))
    return engine


def capture_failing_trace() -> CapturedTrace:
    """Run a retry-exhausted failing question through the pipeline, recording spans."""
    from nl2sql.schema_index import build_schema_index

    engine = _build_engine()
    index = build_schema_index(engine)
    recorder = TraceRecorder()
    obs.set_client(recorder)
    try:
        state = run_pipeline(
            QUESTION,
            schema_index=index,
            engine=engine,
            dialect="sqlite",
            client=_AlwaysWrongClient(),
            max_attempts=2,
            redaction_policy=RedactionPolicy.from_ddl(DDL),
        )
    finally:
        obs.reset_client()
    assert recorder.root is not None, "no trace was recorded"
    terminal = classify_terminal_state(state)
    return CapturedTrace(root=recorder.root, state=state, terminal=terminal)


# --- rendering ---------------------------------------------------------------


def _span_lines(span: Span, depth: int = 0) -> list[str]:
    """A flat, indented text view of the trace tree — the console proof."""
    indent = "  " * depth
    detail = []
    out = span.output or {}
    if "retrieved_tables" in out:
        detail.append(f"tables={out['retrieved_tables']}")
    if "candidate_sql" in out:
        detail.append(f"sql={out['candidate_sql']!r}")
    if "decision" in out:
        detail.append(f"guard={out['decision']}")
    if "error" in out:
        detail.append(f"error={out['error']}")
    if "redacted_columns" in out:
        detail.append(f"redacted={out['redacted_columns']}")
    if "corrected" in out:
        detail.append(f"corrected={out['corrected']}")
    level = f" [{span.level}]" if span.level else ""
    line = f"{indent}• {span.name}{level}  " + " ".join(detail)
    lines = [line.rstrip()]
    for child in span.children:
        lines.extend(_span_lines(child, depth + 1))
    return lines


def _detail_html(span: Span) -> str:
    """The interesting key/values for a span, as HTML chips."""
    out = span.output or {}
    keys = (
        "retrieved_tables",
        "retrieval_mode",
        "candidate_sql",
        "decision",
        "rule",
        "row_count",
        "error",
        "corrected",
        "redacted_columns",
        "presented",
    )
    chips = []
    for k in keys:
        if k in out:
            chips.append(
                f'<span class="chip"><b>{k}</b>{html.escape(str(out[k]))}</span>'
            )
    if span.usage:
        usage = html.escape(str(span.usage))
        chips.append(f'<span class="chip"><b>tokens</b>{usage}</span>')
    if span.duration_ms is not None:
        chips.append(f'<span class="chip dur">{span.duration_ms:.2f} ms</span>')
    return "".join(chips)


def _span_html(span: Span) -> str:
    # Flag a span red when it raised (level=ERROR) or recorded an execution error
    # in its output — the latter is the gracefully-handled DB failure ``execute``
    # surfaces without raising, and is exactly what a debugger scans the trace for.
    errored = span.level == "ERROR" or bool((span.output or {}).get("error"))
    cls = "span err" if errored else "span"
    badge = "generation" if span.as_type == "generation" else "span"
    kids = "".join(_span_html(c) for c in span.children)
    status = (
        f'<span class="status">{html.escape(span.status_message)}</span>'
        if span.status_message
        else ""
    )
    return (
        f'<div class="{cls}"><div class="row">'
        f'<span class="name">{html.escape(span.name)}</span>'
        f'<span class="type">{badge}</span>{status}</div>'
        f'<div class="detail">{_detail_html(span)}</div>'
        f"{kids}</div>"
    )


def render_html(trace: CapturedTrace) -> str:
    spans = trace.root.walk()
    n_attempts = trace.state.attempts
    q = html.escape(QUESTION)
    meta = f"{len(spans)} spans · {n_attempts} attempts"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Example trace — a failing question, diagnosable from its spans</title>
<style>
  body{{margin:0;background:linear-gradient(180deg,#0b1120,#0f172a);color:#e2e8f0;
    line-height:1.5;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}}
  .wrap{{max-width:920px;margin:0 auto;padding:2rem 1.25rem}}
  .badge{{display:inline-block;font-size:.74rem;text-transform:uppercase;
    letter-spacing:.05em;color:#38bdf8;border:1px solid rgba(56,189,248,.35);
    background:rgba(56,189,248,.08);padding:.2rem .6rem;border-radius:999px;
    font-weight:700}}
  h1{{font-size:1.5rem;margin:.7rem 0 .3rem}}
  .q{{color:#94a3b8;margin:.2rem 0 1.2rem}} .q code{{color:#818cf8}}
  .term{{display:inline-block;background:rgba(248,113,113,.12);
    border:1px solid rgba(248,113,113,.4);color:#fca5a5;padding:.35rem .7rem;
    border-radius:8px;font-weight:700;font-size:.9rem;margin-bottom:1.4rem}}
  .span{{border:1px solid #334155;border-left:3px solid #38bdf8;border-radius:10px;
    background:#1e293b;padding:.7rem .9rem;margin:.55rem 0}}
  .span .span{{margin-left:1.4rem;background:#243047}}
  .span.err{{border-left-color:#f87171}}
  .row{{display:flex;align-items:center;gap:.6rem}}
  .name{{font-weight:700;font-size:1rem}}
  .type{{font-size:.66rem;text-transform:uppercase;letter-spacing:.04em;
    color:#94a3b8;border:1px solid #334155;border-radius:5px;padding:.05rem .4rem}}
  .status{{color:#fca5a5;font-size:.8rem;font-family:ui-monospace,Menlo,monospace}}
  .detail{{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.5rem}}
  .chip{{font-size:.78rem;background:#0f172a;border:1px solid #334155;
    border-radius:6px;padding:.15rem .45rem;color:#cbd5e1;
    font-family:ui-monospace,Menlo,monospace;max-width:100%;overflow-wrap:anywhere}}
  .chip b{{color:#38bdf8;margin-right:.35rem;font-weight:700}}
  .chip.dur{{color:#94a3b8}}
  .legend{{color:#94a3b8;font-size:.82rem;margin-top:1.6rem;
    border-top:1px solid #334155;padding-top:1rem}}
  .legend b{{color:#34d399}}
</style></head>
<body><div class="wrap">
  <span class="badge">Step 8 · example trace · offline-captured</span>
  <h1>A failing question, diagnosable from its trace</h1>
  <p class="q">Question: <code>{q}</code> · {meta}</p>
  <div class="term">terminal state: {trace.terminal.value}</div>
  {_span_html(trace.root)}
  <div class="legend">
    Captured offline by <b>eval.prove_step8</b> with an in-process recorder standing
    in for Langfuse — the trace shape is identical once a key is supplied. Every span
    carries only shapes, counts, the generated SQL, the guard verdict, and the
    exception <em>class</em>; the <b>redact</b> span shows the presented exit (no
    result on a failed run) and no raw PII value appears anywhere on the trace.
  </div>
</div></body></html>
"""


def main() -> int:
    trace = capture_failing_trace()
    print(f"\nQuestion: {QUESTION}")
    print(f"terminal: {trace.terminal.value}  (attempts={trace.state.attempts})\n")
    print("\n".join(_span_lines(trace.root)))

    # Defensive: the captured trace must never carry a raw PII value. A hard
    # raise, not an ``assert`` — a security gate must not vanish under ``python -O``.
    rendered = render_html(trace)
    for secret in ("alice@secret.example", "Alice Lee"):
        if secret in rendered:
            raise RuntimeError(f"PII leaked into the trace: {secret!r}")

    ARTIFACT.write_text(rendered)
    print(f"\nwrote example trace → {ARTIFACT.relative_to(ARTIFACT.parents[3])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
