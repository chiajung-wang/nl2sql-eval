-- Payments-platform demo schema (PostgreSQL).
--
-- Hand-built qualitative showcase for the NL-to-SQL system. Small but realistic.
-- Two deliberate properties drive later steps:
--   * PII columns (users.email/full_name/phone, payment_methods.last4/...) motivate
--     the column-aware redaction work in Step 8.
--   * `ledger` is the write-sensitive financial source of truth — it motivates the
--     read-only / dangerous-op guardrails in Step 4.
--
-- Idempotent: drops the tables (FK-respecting order) before recreating them so the
-- loader can be re-run against a live db.

DROP TABLE IF EXISTS ledger        CASCADE;
DROP TABLE IF EXISTS disputes      CASCADE;
DROP TABLE IF EXISTS refunds       CASCADE;
DROP TABLE IF EXISTS transactions  CASCADE;
DROP TABLE IF EXISTS payment_methods CASCADE;
DROP TABLE IF EXISTS merchants     CASCADE;
DROP TABLE IF EXISTS users         CASCADE;

-- Customers. Carries the most obvious PII (email, full_name, phone).
CREATE TABLE users (
    id          INTEGER PRIMARY KEY,
    email       TEXT        NOT NULL UNIQUE,   -- PII
    full_name   TEXT        NOT NULL,          -- PII
    phone       TEXT,                          -- PII
    country     CHAR(2)     NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Businesses that accept payments.
CREATE TABLE merchants (
    id          INTEGER PRIMARY KEY,
    name        TEXT        NOT NULL,
    category    TEXT        NOT NULL,
    country     CHAR(2)     NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stored payment instruments. `last4` / brand / expiry are sensitive cardholder data.
CREATE TABLE payment_methods (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users (id),
    method_type TEXT        NOT NULL CHECK (method_type IN ('card', 'bank_account')),
    brand       TEXT,                          -- e.g. visa, mastercard (PII-adjacent)
    last4       CHAR(4)     NOT NULL,          -- PII (cardholder data)
    exp_month   SMALLINT    CHECK (exp_month BETWEEN 1 AND 12),
    exp_year    SMALLINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Payment attempts. The high-volume fact table.
CREATE TABLE transactions (
    id                INTEGER     PRIMARY KEY,
    user_id           INTEGER     NOT NULL REFERENCES users (id),
    merchant_id       INTEGER     NOT NULL REFERENCES merchants (id),
    payment_method_id INTEGER     NOT NULL REFERENCES payment_methods (id),
    amount_cents      BIGINT      NOT NULL CHECK (amount_cents > 0),
    currency          CHAR(3)     NOT NULL DEFAULT 'USD',
    status            TEXT        NOT NULL CHECK (status IN ('captured', 'pending', 'failed', 'refunded')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Full or partial reversals of a captured transaction.
CREATE TABLE refunds (
    id              INTEGER     PRIMARY KEY,
    transaction_id  INTEGER     NOT NULL REFERENCES transactions (id),
    amount_cents    BIGINT      NOT NULL CHECK (amount_cents > 0),
    reason          TEXT,
    status          TEXT        NOT NULL CHECK (status IN ('succeeded', 'pending', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Customer-initiated chargebacks against a transaction.
CREATE TABLE disputes (
    id              INTEGER     PRIMARY KEY,
    transaction_id  INTEGER     NOT NULL REFERENCES transactions (id),
    amount_cents    BIGINT      NOT NULL CHECK (amount_cents > 0),
    reason          TEXT        NOT NULL,
    status          TEXT        NOT NULL CHECK (status IN ('open', 'won', 'lost', 'withdrawn')),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

-- Double-entry-style financial record. Write-sensitive: the source of truth that
-- guardrails must protect from writes/DDL (read-only enforcement, Step 4).
CREATE TABLE ledger (
    id                  INTEGER     PRIMARY KEY,
    transaction_id      INTEGER     REFERENCES transactions (id),
    entry_type          TEXT        NOT NULL CHECK (entry_type IN ('debit', 'credit')),
    amount_cents        BIGINT      NOT NULL CHECK (amount_cents > 0),
    balance_after_cents BIGINT      NOT NULL,
    account             TEXT        NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
