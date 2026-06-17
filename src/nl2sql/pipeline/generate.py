"""Stage: generate — LLM produces candidate SQL from question + schema.

Step 1 (issue 4) made one direct Anthropic SDK call here. Step 7 (issue #51)
routes that call through the ``nl2sql.llm`` boundary (LiteLLM under the hood), so
the provider is selectable by the ``model`` identifier without this stage
changing — the cross-provider cost/accuracy table (#52) becomes trivial. The
prompt is still loaded from an externalized template in ``prompts/`` (CI diffs
that dir — never inline prompt strings here).

Decoupling: this stage takes the schema as an argument. The pipeline is
import-shared by ``eval/`` and ``apps/demo/`` and must not depend on either, so
the caller (later: harness / demo) owns where the schema text comes from.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from nl2sql.llm import LLMClient, default_client
from nl2sql.obs import stage_span
from nl2sql.pipeline.state import RunState

# Default to a current, capable Claude model (Sonnet 4.x) per CLAUDE.md §2,
# provider-prefixed for LiteLLM routing (``anthropic/`` = a direct provider key).
DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"
MAX_TOKENS = 1024

# Templates live at the repo-root ``prompts/`` dir (CI diffs them), three
# parents up from src/nl2sql/pipeline/generate.py.
PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
GENERATE_TEMPLATE = "generate/v3.jinja"
# The prompt version recorded alongside every reported number (CLAUDE.md §6).
PROMPT_VERSION = "generate/v3"

# Default dialect — the payments demo is PostgreSQL; the BIRD path passes
# "SQLite". A variable (not hardcoded) so the prompt measures generation quality
# rather than dialect mismatch on a non-Postgres benchmark.
DEFAULT_DIALECT = "PostgreSQL"

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


def render_prompt(
    schema: str,
    question: str,
    *,
    dialect: str = DEFAULT_DIALECT,
    evidence: str = "",
    correction: dict[str, str] | None = None,
) -> str:
    """Render the externalized generate template with the schema dumped inline.

    ``dialect`` selects the SQL flavor named in the prompt; ``evidence`` is an
    optional external-knowledge hint (BIRD ships one per question) that is
    omitted from the prompt when empty. ``correction`` is the prior failed
    attempt's ``{sql, error}`` (Step 5 self-correction); ``None`` on the first
    attempt, in which case the rendered prompt is identical to v2.
    """
    template = _env().get_template(GENERATE_TEMPLATE)
    return template.render(
        schema=schema,
        question=question,
        dialect=dialect,
        evidence=evidence,
        correction=correction,
    )


def _extract_sql(text: str) -> str:
    """Unwrap a markdown fence from the model response (presentation only).

    NOT semantic SQL handling — no parsing of meaning here. The "no regex for
    SQL" rule (CLAUDE.md §4) governs semantics (table scope, write detection),
    which is sqlglot's job downstream in guard/.
    """
    match = _FENCE_RE.match(text)
    return (match.group("body") if match else text).strip()


def generate(
    state: RunState,
    schema: str,
    *,
    dialect: str = DEFAULT_DIALECT,
    evidence: str = "",
    model: str = DEFAULT_MODEL,
    client: LLMClient | None = None,
) -> RunState:
    """Generate candidate SQL for ``state.question`` and store it on the state.

    One completion through the ``nl2sql.llm`` boundary (LiteLLM under the hood);
    ``model`` selects the provider (``anthropic/...`` direct, ``openrouter/...``
    aggregated). ``dialect``/``evidence`` are threaded into the prompt (SQLite +
    the BIRD hint on the benchmark path; PostgreSQL + no hint on the payments
    demo). On a retry, ``state.correction`` (set by the ``correct`` stage) feeds
    the prior failed SQL + error back into the prompt. ``client`` is injectable so
    tests can run without a network/API key. Mutates and returns ``state``.
    """
    with stage_span("generate", db_id=state.db_id, model=model) as extra:
        prompt = render_prompt(
            schema,
            state.question,
            dialect=dialect,
            evidence=evidence,
            correction=state.correction,
        )
        client = client or default_client()

        response = client.complete(prompt, model=model, max_tokens=MAX_TOKENS)
        state.candidate_sql = _extract_sql(response.text)

        # candidate_sql is generated SQL (no PII); safe to attach to the span.
        extra["candidate_sql"] = state.candidate_sql
        if response.input_tokens is not None or response.output_tokens is not None:
            extra["input_tokens"] = response.input_tokens
            extra["output_tokens"] = response.output_tokens
            # Accumulate token usage across attempts on the state so the harness
            # can price the run's *total* cost — a retry is never free (Step 5,
            # issue #43). Per-call counts stay on the span; the running totals
            # live in meta.
            state.meta["input_tokens"] = state.meta.get("input_tokens", 0) + (
                response.input_tokens or 0
            )
            state.meta["output_tokens"] = state.meta.get("output_tokens", 0) + (
                response.output_tokens or 0
            )

    return state
