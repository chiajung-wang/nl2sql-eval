# Issue 2 — Payments Postgres database

**Type:** AFK
**Phase:** Step 1 (Foundation) — *Prove the machine runs end-to-end*

## Parent

`docs/plans/step-1/plan-step-1.md`

## What to build

The payments-platform database that the demo and guardrail/redaction work are built around — a hand-built qualitative showcase, run locally on Postgres via Docker. Volume stays small but realistic.

Includes:
- A `docker-compose` definition bringing up a local Postgres instance.
- DDL for the seven tables: `users`, `merchants`, `transactions`, `payment_methods`, `refunds`, `disputes`, `ledger`. Deliberately include:
  - **PII columns** (e.g. `users.email`, and other obvious personal fields) — these motivate Step 8 redaction.
  - A **write-sensitive `ledger`** — motivates the read-only / dangerous-op guardrails in Step 4.
- A small, realistic seed dataset across all tables (consistent foreign keys, a few refunds/disputes, ledger entries).
- A load/bootstrap script that applies the DDL and seed to the running Postgres.
- DDL lives under `eval/datasets/payments/` per PRD §8.

## Acceptance criteria

- [ ] `docker compose up` brings up Postgres locally.
- [ ] Running the load script creates all seven tables and populates seed data.
- [ ] PII columns (incl. `users.email`) and a write-sensitive `ledger` table are present.
- [ ] A sample `SELECT` (e.g. join transactions to users) returns the expected seeded rows.
- [ ] `PAYMENTS_DB_URL` (or equivalent config) connects a SQLAlchemy engine to the running db.

## Blocked by

None — can start immediately.
