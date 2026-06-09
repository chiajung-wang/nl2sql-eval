"""Bootstrap the payments demo database: apply DDL + seed, then verify.

Run against a live Postgres (see docker-compose.yml at the repo root):

    docker compose up -d
    uv run python -m eval.datasets.payments.load

Connection comes from ``PAYMENTS_DB_URL`` (a SQLAlchemy URL); it defaults to the
docker-compose credentials. The script is idempotent — ``schema.sql`` drops and
recreates the tables before ``seed.sql`` repopulates them — so re-running it
resets the db to a known state.

This is the issue-2 dataset bootstrap only. Pipeline execution (the multi-engine
SQLAlchemy executor) lands separately in ``src/nl2sql/pipeline/execute.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_DB_URL = "postgresql://payments:payments@localhost:5432/payments"

_HERE = Path(__file__).parent
SCHEMA_SQL = _HERE / "schema.sql"
SEED_SQL = _HERE / "seed.sql"

# The full table set the loader must create (acceptance: all seven present).
TABLES = (
    "users",
    "merchants",
    "payment_methods",
    "transactions",
    "refunds",
    "disputes",
    "ledger",
)


def get_engine(db_url: str | None = None) -> Engine:
    """SQLAlchemy engine for the payments db (``PAYMENTS_DB_URL`` or default)."""
    url = db_url or os.environ.get("PAYMENTS_DB_URL", DEFAULT_DB_URL)
    return create_engine(url, future=True)


def load_payments(engine: Engine) -> None:
    """Apply the DDL then the seed data in a single transaction."""
    schema = SCHEMA_SQL.read_text()
    seed = SEED_SQL.read_text()
    with engine.begin() as conn:
        # exec_driver_sql passes the raw, multi-statement script to the driver.
        conn.exec_driver_sql(schema)
        conn.exec_driver_sql(seed)


def verify(engine: Engine) -> None:
    """Sanity-check the load: all seven tables present, sample join returns rows."""
    with engine.connect() as conn:
        print("Row counts:")
        for table in TABLES:
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            print(f"  {table:<16} {count:>4}")

        print("\nSample join (transactions → users → merchants), first 5 captured:")
        rows = conn.execute(
            text(
                """
                SELECT t.id, u.full_name, m.name AS merchant,
                       t.amount_cents, t.currency, t.status
                FROM transactions t
                JOIN users u     ON u.id = t.user_id
                JOIN merchants m ON m.id = t.merchant_id
                WHERE t.status = 'captured'
                ORDER BY t.id
                LIMIT 5
                """
            )
        ).all()
        for row in rows:
            print(
                f"  {row.id:>2}  {row.full_name:<14} {row.merchant:<22} "
                f"{row.amount_cents:>6} {row.currency}  {row.status}"
            )


def main() -> None:
    engine = get_engine()
    print(f"Connecting to {engine.url.render_as_string(hide_password=True)}")
    load_payments(engine)
    print("Loaded schema.sql + seed.sql.\n")
    verify(engine)


if __name__ == "__main__":
    main()
