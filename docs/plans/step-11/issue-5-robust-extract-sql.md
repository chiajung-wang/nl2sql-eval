# Issue 5 — Robust `_extract_sql` for reasoning-model output

**Type:** AFK
**Phase:** Step 11 follow-up (Optimization) — *pipeline robustness; unblocks reasoning-model generators*

## Parent

`docs/plans/step-11/plan-step-11.md`

## Motivation (what the diagnostic surfaced)

While re-baselining generators (#117 follow-up), `openrouter/google/gemini-3.5-flash` scored a misleading **pass@1 0.280 (14/50)** — but the diagnostic showed **25/50 candidates tagged `candidate_unparseable` and guardrail-rejected**. The cause is not SQL quality: `gemini-3.5-flash` is a **reasoning model** that emits chain-of-thought prose around the SQL, and the generate stage's extractor only handles a reply that is *entirely* clean SQL or *entirely* one fenced block:

```python
# src/nl2sql/pipeline/generate.py
_FENCE_RE = re.compile(r"^\s*```(?:sql)?\s*(?P<body>.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)
def _extract_sql(text):
    match = _FENCE_RE.match(text)          # anchored ^…$ — the WHOLE reply must be one fence
    return (match.group("body") if match else text).strip()
```

Any preamble before the fence fails the anchored match, so the entire prose blob falls through unparsed → `guard` rejects it. This is the **same root cause** as the `candidate_unparseable` spike observed under the #113 few-shot prompt on a weak generator. Reasoning-style models are increasingly common, so this is a latent correctness/robustness bug that silently penalizes them.

## What to build

Make `_extract_sql` robust to surrounding prose, **as presentation-only string handling** — it must not do any SQL *semantics* (table scope, write detection, validity stay with sqlglot in `guard/`, per CLAUDE.md §4 / §7):

- **Find a fenced ```` ```sql ```` block anywhere in the reply**, not only when it spans the whole message. Prefer the **last** fenced block (reasoning models put the final answer last; earlier fences may be scratch work).
- **No-fence fallback:** if there is no fenced block, locate the SQL by the last statement opener (`SELECT` / `WITH`, case-insensitive, word-boundary) and take from there to the end — a presentation heuristic, not semantic parsing. sqlglot still validates downstream; a wrong guess is rejected exactly as today.
- **Preserve current behavior for clean replies:** a bare-SQL reply and a single whole-reply fence must extract byte-identically to today (no regression for sonnet / flash-lite, which already return clean SQL).

## Acceptance criteria

- [ ] `_extract_sql` extracts correctly for: bare SQL (unchanged), single whole-reply fence (unchanged), **preamble + fence**, **multiple fences (returns the last)**, **no fence with reasoning preamble**, and trailing prose after the SQL
- [ ] No SQL semantics introduced — extraction is presentation-only; `guard` (sqlglot AST) remains the sole validator
- [ ] Unit tests cover every case above; existing generate/guard tests stay green
- [ ] `uv run pytest` green; lint/format clean
- [ ] **(Deferred live run, gated on key/spend — [[defer-api-key-verification]])** re-baseline `gemini-3.5-flash` on the dev slice showing `candidate_unparseable` 25 → ~0 and its true pass@1; recorded in `RESULTS.md` with full config + commit

## Out of scope

- Changing the active model or the pinned `DEFAULT_MODEL`.
- Any semantic SQL handling in the extractor (stays sqlglot's job in `guard`).
- Enabling/forcing provider `reasoning` parameters — this issue handles whatever the model returns in `content`.

## Blocked by

- None (independent). Motivated by the #117 follow-up finding; pairs naturally with re-baselining the reasoning-class generators afterward.

---

## Tracking

**GitHub:** _to be filed_ · label `agent-ready`, `step-11`

**PR:** _pending_

**Step 11 follow-up set:** #5 (this) · #6 (join/table semantics)
