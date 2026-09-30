"""DuckDB helpers: connect, set variables, run the SQL files in order."""
from __future__ import annotations

from pathlib import Path

import duckdb

from . import config

FEATURE_SQL = [
    "02_transactions.sql",
    "03_customer_month.sql",
    "04_customer_quarter.sql",
    "05_customer_features.sql",
]
TRIGGER_SQL = "06_triggers.sql"


def connect(path: Path | str | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = config.DB_PATH if path is None else path
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def set_variables(con: duckdb.DuckDBPyConnection, params: dict) -> None:
    for name, value in params.items():
        literal = f"'{value}'" if isinstance(value, str) else repr(value)
        con.execute(f"SET VARIABLE {name} = {literal}")


def run_sql_file(con: duckdb.DuckDBPyConnection, filename: str) -> None:
    con.execute((config.SQL_DIR / filename).read_text(encoding="utf-8"))


def build_features(con: duckdb.DuckDBPyConnection) -> None:
    """Run every feature SQL file. Expects a raw_transactions table to exist."""
    for filename in FEATURE_SQL:
        run_sql_file(con, filename)


def build_triggers(con: duckdb.DuckDBPyConnection, params: dict | None = None) -> None:
    """Run the trigger SQL. Expects customer_month and transactions to exist."""
    set_variables(con, {**config.TRIGGER_PARAMS, **(params or {})})
    run_sql_file(con, TRIGGER_SQL)
