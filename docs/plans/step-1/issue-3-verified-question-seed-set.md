# Issue 3 — Verified question seed set

**Type:** AFK (with human review checkbox)
**Phase:** Step 1 (Foundation) — *Prove the machine runs end-to-end*

## Parent

`docs/plans/step-1/plan-step-1.md`

## What to build

A handful of hand-authored payments questions paired with **gold answers you know cold**. This is the trusted ground that Step 3 validates the harness against before it is ever pointed at BIRD — so correctness of the gold matters more than quantity here.

Includes:
- A small set (e.g. 5–10) of natural-language questions over the payments schema, spanning easy lookups to a couple of joins/aggregations.
- For each: the verified gold result (and, where useful, the gold SQL that produces it) consistent with the seeded data from Issue 2.
- Stored under `eval/datasets/payments/` alongside the schema.
- An explicit human-review pass confirming each gold answer is actually correct against the seeded rows (the AFK agent drafts; a human ticks the review box).

## Acceptance criteria

- [ ] A committed question set (≈5–10 Q/A pairs) over the payments schema exists under `eval/datasets/payments/`.
- [ ] Each question has a gold answer (and gold SQL where applicable) consistent with the Issue 2 seed data.
- [ ] Questions span a range from simple lookups to at least one join and one aggregation.
- [ ] **Human review:** each gold answer has been eyeballed against the seeded data and confirmed correct.

## Blocked by

- Issue 2 — Payments Postgres database (gold answers depend on the seed).
