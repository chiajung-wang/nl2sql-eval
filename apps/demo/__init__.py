"""Thin demo UI — reveals the wrapper, isolated dep group (Step 10, #62).

Imports the *same* pipeline the harness runs (``nl2sql.pipeline.graph``) and the
*same* terminal-state classifier the harness uses (``eval.harness``) — never a
fork, so the demo can't drift from the measured numbers. The logic lives in a
testable core (:mod:`apps.demo.runner`); ``app.py`` is a thin Streamlit shell
over it. The point is to surface the **machinery** — guardrail decision, retry
count, cost, terminal state, and the *presented (redacted)* result — not to hide
a chatbot.
"""
