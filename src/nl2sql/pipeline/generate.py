"""Stage: generate — LLM produces candidate SQL from question + schema.

Step 1 (issue 4): one direct Anthropic SDK call with the schema dumped inline
and the prompt loaded from an externalized template in ``prompts/``. LiteLLM
swaps in at Step 7.

Stub — implemented in docs/plans/step-1/issue-4.
"""
