-- Payments-platform demo seed data (PostgreSQL).
--
-- Small but realistic, with consistent foreign keys: 6 users, 4 merchants,
-- 7 payment methods, 14 transactions, 2 refunds, 2 disputes, 12 ledger entries.
-- Explicit ids and timestamps keep the seeded answers deterministic so the
-- hand-written verified questions (issue 3) have answers we know cold.
--
-- Idempotent: schema.sql drops/recreates the tables first, so this file just
-- inserts.

-- Customers (note the PII: email, full_name, phone).
INSERT INTO users (id, email, full_name, phone, country, created_at) VALUES
    (1, 'alice.nguyen@example.com', 'Alice Nguyen',  '+1-415-555-0101',  'US', '2026-01-04 09:12:00+00'),
    (2, 'bob.martins@example.com',  'Bob Martins',   '+1-212-555-0148',  'US', '2026-01-09 14:03:00+00'),
    (3, 'carla.diaz@example.com',   'Carla Diaz',    '+34-600-555-201',  'ES', '2026-01-15 08:47:00+00'),
    (4, 'derek.owusu@example.co.uk','Derek Owusu',   '+44-7700-900502',  'GB', '2026-01-22 17:30:00+00'),
    (5, 'emi.tanaka@example.jp',    'Emi Tanaka',    '+81-90-5550-3001', 'JP', '2026-02-01 23:55:00+00'),
    (6, 'farah.haidar@example.com', 'Farah Haidar',  '+1-312-555-0173',  'US', '2026-02-10 11:18:00+00');

-- Merchants.
INSERT INTO merchants (id, name, category, country, created_at) VALUES
    (1, 'BrewHaus Coffee',       'food_and_drink', 'US', '2025-11-01 00:00:00+00'),
    (2, 'CloudNine SaaS',        'software',       'US', '2025-11-05 00:00:00+00'),
    (3, 'Trailhead Outfitters',  'retail',         'US', '2025-12-12 00:00:00+00'),
    (4, 'LumaBooks',             'books',          'ES', '2026-01-02 00:00:00+00');

-- Stored payment instruments (last4 / brand / expiry are sensitive).
INSERT INTO payment_methods (id, user_id, method_type, brand, last4, exp_month, exp_year, created_at) VALUES
    (1, 1, 'card',         'visa',       '4242', 12, 2027, '2026-01-04 09:15:00+00'),
    (2, 2, 'card',         'mastercard', '5454',  3, 2026, '2026-01-09 14:05:00+00'),
    (3, 3, 'card',         'visa',       '4111',  9, 2028, '2026-01-15 08:50:00+00'),
    (4, 4, 'bank_account', NULL,         '6789', NULL, NULL, '2026-01-22 17:35:00+00'),
    (5, 5, 'card',         'amex',       '0005', 11, 2026, '2026-02-01 23:58:00+00'),
    (6, 6, 'card',         'visa',       '1881',  7, 2027, '2026-02-10 11:20:00+00'),
    (7, 1, 'card',         'mastercard', '8210',  1, 2029, '2026-02-14 10:00:00+00');

-- Transactions (the fact table). Mix of captured / pending / failed / refunded.
INSERT INTO transactions (id, user_id, merchant_id, payment_method_id, amount_cents, currency, status, created_at) VALUES
    ( 1, 1, 1, 1,    550, 'USD', 'captured', '2026-02-15 08:30:00+00'),
    ( 2, 1, 2, 7,   1999, 'USD', 'captured', '2026-02-16 12:00:00+00'),
    ( 3, 2, 1, 2,    750, 'USD', 'captured', '2026-02-16 09:05:00+00'),
    ( 4, 2, 3, 2,  12500, 'USD', 'refunded', '2026-02-17 15:42:00+00'),
    ( 5, 3, 4, 3,   2200, 'EUR', 'captured', '2026-02-18 10:11:00+00'),
    ( 6, 3, 2, 3,   1999, 'USD', 'failed',   '2026-02-18 10:14:00+00'),
    ( 7, 4, 3, 4,   8999, 'GBP', 'captured', '2026-02-19 18:20:00+00'),
    ( 8, 4, 1, 4,    425, 'GBP', 'pending',  '2026-02-20 07:45:00+00'),
    ( 9, 5, 2, 5,   1999, 'USD', 'captured', '2026-02-21 22:30:00+00'),
    (10, 5, 4, 5,   3500, 'JPY', 'captured', '2026-02-22 13:05:00+00'),
    (11, 6, 3, 6,   6400, 'USD', 'refunded', '2026-02-23 16:50:00+00'),
    (12, 6, 1, 6,    500, 'USD', 'captured', '2026-02-24 08:02:00+00'),
    (13, 2, 2, 2,   1999, 'USD', 'pending',  '2026-02-25 11:30:00+00'),
    (14, 1, 3, 1,   4500, 'USD', 'failed',   '2026-02-26 19:15:00+00');

-- Refunds against the two 'refunded' transactions (one full, one partial).
INSERT INTO refunds (id, transaction_id, amount_cents, reason, status, created_at) VALUES
    (1,  4, 12500, 'customer_request',   'succeeded', '2026-02-18 09:00:00+00'),
    (2, 11,  3200, 'item_not_received',  'succeeded', '2026-02-24 10:30:00+00');

-- Disputes (chargebacks) against captured transactions.
INSERT INTO disputes (id, transaction_id, amount_cents, reason, status, opened_at, resolved_at) VALUES
    (1, 7, 8999, 'product_not_received', 'open', '2026-02-22 09:00:00+00', NULL),
    (2, 9, 1999, 'fraudulent',           'lost', '2026-02-24 14:00:00+00', '2026-03-02 16:20:00+00');

-- Ledger: running platform-clearing balance. Credits on captured/refunded
-- transactions, debits matching the two refunds. Write-sensitive (guardrails).
INSERT INTO ledger (id, transaction_id, entry_type, amount_cents, balance_after_cents, account, created_at) VALUES
    ( 1,  1, 'credit',   550,   550, 'platform_clearing', '2026-02-15 08:30:05+00'),
    ( 2,  2, 'credit',  1999,  2549, 'platform_clearing', '2026-02-16 12:00:05+00'),
    ( 3,  3, 'credit',   750,  3299, 'platform_clearing', '2026-02-16 09:05:05+00'),
    ( 4,  4, 'credit', 12500, 15799, 'platform_clearing', '2026-02-17 15:42:05+00'),
    ( 5,  4, 'debit',  12500,  3299, 'platform_clearing', '2026-02-18 09:00:05+00'),
    ( 6,  5, 'credit',  2200,  5499, 'platform_clearing', '2026-02-18 10:11:05+00'),
    ( 7,  7, 'credit',  8999, 14498, 'platform_clearing', '2026-02-19 18:20:05+00'),
    ( 8,  9, 'credit',  1999, 16497, 'platform_clearing', '2026-02-21 22:30:05+00'),
    ( 9, 10, 'credit',  3500, 19997, 'platform_clearing', '2026-02-22 13:05:05+00'),
    (10, 11, 'credit',  6400, 26397, 'platform_clearing', '2026-02-23 16:50:05+00'),
    (11, 11, 'debit',   3200, 23197, 'platform_clearing', '2026-02-24 10:30:05+00'),
    (12, 12, 'credit',   500, 23697, 'platform_clearing', '2026-02-24 08:02:05+00');
