"""SQLite persistence for the portfolio analysis outputs."""

import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Mapping

import pandas as pd


_EXPECTED_TABLES = frozenset(
    {"prices", "asset_metrics", "portfolio_metrics", "portfolio_weights"}
)


def write_analysis_database(
    path: str | Path, tables: Mapping[str, pd.DataFrame]
) -> None:
    """Atomically replace ``path`` with the complete analysis database."""
    _validate_table_names(tables)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)

    try:
        connection = sqlite3.connect(temporary_path)
        try:
            with connection:
                for name, table in tables.items():
                    table.to_sql(name, connection, index=False)
                connection.execute(
                    "CREATE INDEX idx_prices_symbol_date ON prices (symbol, date)"
                )
        finally:
            connection.close()
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _validate_table_names(tables: Mapping[str, pd.DataFrame]) -> None:
    """Ensure consumers receive exactly the storage schema they expect."""
    actual_names = set(tables)
    if actual_names != _EXPECTED_TABLES:
        raise ValueError("Expected exactly the analysis tables")
