"""LLM provider abstraction.

Step 1: a direct single-provider call (Anthropic) lives behind this boundary.
Step 7 swaps in LiteLLM for multi-provider cost/accuracy comparison without the
pipeline changing.

Stub — direct provider lands in docs/plans/step-1/issue-4; LiteLLM in step-7.
"""
