"""LLM provider abstraction.

Step 1 keeps it thin: the direct Anthropic SDK call lives inline in the
``generate`` stage (one provider, called directly). This module is where that
call moves behind a provider boundary at Step 7, when LiteLLM swaps in for
multi-provider cost/accuracy comparison without the pipeline changing.

Stub — LiteLLM provider abstraction lands in step-7.
"""
