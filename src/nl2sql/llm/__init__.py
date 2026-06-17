"""LLM provider abstraction.

The pipeline talks to exactly one seam — the ``LLMClient`` protocol — and never
to a vendor SDK. Step 7 (issue #51) backs that seam with **LiteLLM** for
multi-provider cost/accuracy comparison without the pipeline changing; the
backend (direct provider key vs. an OpenRouter aggregator) is selected purely by
the model identifier the caller passes. See ``client.py``.
"""

from nl2sql.llm.client import (
    REQUEST_MAX_RETRIES,
    REQUEST_TIMEOUT_S,
    LiteLLMClient,
    LLMClient,
    LLMResponse,
    default_client,
)

__all__ = [
    "LLMClient",
    "LLMResponse",
    "LiteLLMClient",
    "default_client",
    "REQUEST_TIMEOUT_S",
    "REQUEST_MAX_RETRIES",
]
