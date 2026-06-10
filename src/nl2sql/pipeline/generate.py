"""Stage: generate — LLM produces candidate SQL from question + schema.

Step 1 (issue 4): one direct Anthropic SDK call with the schema dumped inline
and the prompt loaded from an externalized template in ``prompts/`` (CI diffs
that dir — never inline prompt strings here). The single-provider call lives
behind this stage today; LiteLLM swaps in at Step 7 without the pipeline
changing.

Decoupling: this stage takes the schema as an argument. The pipeline is
import-shared by ``eval/`` and ``apps/demo/`` and must not depend on either, so
the caller (later: harness / demo) owns where the schema text comes from.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState

# Default to a current, capable Claude model (Sonnet 4.x) per CLAUDE.md §2.
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# Templates live at the repo-root ``prompts/`` dir (CI diffs them), three
# parents up from src/nl2sql/pipeline/generate.py.
PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
GENERATE_TEMPLATE = "generate/v1.jinja"

# Strips a ```sql ... ``` (or bare ```) fence if the model wraps its answer.
_FENCE_RE = re.compile(
    r"^\s*```(?:sql)?\s*(?P<body>.*?)\s*```\s*$",
    re.IGNORECASE | re.DOTALL,
)


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render_prompt(schema: str, question: str) -> str:
    """Render the externalized generate template with the schema dumped inline."""
    template = _env().get_template(GENERATE_TEMPLATE)
    return template.render(schema=schema, question=question)


def _extract_sql(text: str) -> str:
    """Unwrap a markdown fence from the model response (presentation only).

    NOT semantic SQL handling — no parsing of meaning here. The "no regex for
    SQL" rule (CLAUDE.md §4) governs semantics (table scope, write detection),
    which is sqlglot's job downstream in guard/.
    """
    match = _FENCE_RE.match(text)
    return (match.group("body") if match else text).strip()


def _default_client() -> Any:
    """Construct the Anthropic client lazily so importing this module needs no key."""
    from anthropic import Anthropic

    return Anthropic()


def generate(
    state: RunState,
    schema: str,
    *,
    model: str = DEFAULT_MODEL,
    client: Any | None = None,
) -> RunState:
    """Generate candidate SQL for ``state.question`` and store it on the state.

    One direct Anthropic ``messages.create`` call. ``client`` is injectable so
    tests can run without a network/API key. Mutates and returns ``state``.
    """
    with stage_span("generate", db_id=state.db_id, model=model) as extra:
        prompt = render_prompt(schema, state.question)
        client = client or _default_client()

        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        state.candidate_sql = _extract_sql(raw)

        # candidate_sql is generated SQL (no PII); safe to attach to the span.
        extra["candidate_sql"] = state.candidate_sql
        usage = getattr(response, "usage", None)
        if usage is not None:
            extra["input_tokens"] = getattr(usage, "input_tokens", None)
            extra["output_tokens"] = getattr(usage, "output_tokens", None)

    return state
