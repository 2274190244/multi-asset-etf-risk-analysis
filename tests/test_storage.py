import sqlite3
from pathlib import Path
import re

import pandas as pd
import pytest

from portfolio_analysis.storage import write_analysis_database


def test_write_analysis_database_creates_expected_tables(tmp_path):
    db = tmp_path / "analysis.sqlite"
    tables = {
        "prices": pd.DataFrame(
            {"symbol": ["A"], "date": ["2026-01-02"], "close": [10.0]}
        ),
        "asset_metrics": pd.DataFrame({"symbol": ["A"], "annualized_return": [0.1]}),
        "portfolio_metrics": pd.DataFrame(
            {"portfolio": ["equal_weight"], "max_drawdown": [-0.1]}
        ),
        "portfolio_weights": pd.DataFrame(
            {"portfolio": ["equal_weight"], "symbol": ["A"], "weight": [1.0]}
        ),
    }

    write_analysis_database(db, tables)

    with sqlite3.connect(db) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert set(tables).issubset(names)


def test_write_analysis_database_rejects_unexpected_table_names(tmp_path):
    tables = {
        "prices": pd.DataFrame({"value": [1]}),
        "asset_metrics": pd.DataFrame({"value": [1]}),
        "portfolio_metrics": pd.DataFrame({"value": [1]}),
        "unexpected": pd.DataFrame({"value": [1]}),
    }

    with pytest.raises(ValueError, match="Expected exactly the analysis tables"):
        write_analysis_database(tmp_path / "analysis.sqlite", tables)


def test_write_analysis_database_creates_prices_symbol_date_index(tmp_path):
    db = tmp_path / "analysis.sqlite"
    tables = {
        "prices": pd.DataFrame(
            {"symbol": ["A"], "date": ["2026-01-02"], "close": [10.0]}
        ),
        "asset_metrics": pd.DataFrame({"symbol": ["A"]}),
        "portfolio_metrics": pd.DataFrame({"portfolio": ["equal_weight"]}),
        "portfolio_weights": pd.DataFrame(
            {"portfolio": ["equal_weight"], "symbol": ["A"], "weight": [1.0]}
        ),
    }

    write_analysis_database(db, tables)

    with sqlite3.connect(db) as connection:
        index_columns = {
            index[1]: [column[2] for column in connection.execute(f"PRAGMA index_info({index[1]})")]
            for index in connection.execute("PRAGMA index_list('prices')")
        }

    assert index_columns["idx_prices_symbol_date"] == ["symbol", "date"]


def test_write_analysis_database_preserves_destination_when_a_table_write_fails(
    tmp_path, monkeypatch
):
    db = tmp_path / "analysis.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE preserved (label TEXT)")
        connection.execute("INSERT INTO preserved VALUES ('original')")

    tables = {
        "prices": pd.DataFrame(
            {"symbol": ["A"], "date": ["2026-01-02"], "close": [20.0]}
        ),
        "asset_metrics": pd.DataFrame({"symbol": ["A"]}),
        "portfolio_metrics": pd.DataFrame({"portfolio": ["equal_weight"]}),
        "portfolio_weights": pd.DataFrame(
            {"portfolio": ["equal_weight"], "symbol": ["A"], "weight": [1.0]}
        ),
    }
    original_to_sql = pd.DataFrame.to_sql

    def fail_asset_metrics_write(frame, name, connection, *args, **kwargs):
        if name == "asset_metrics":
            raise RuntimeError("simulated write failure")
        return original_to_sql(frame, name, connection, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_sql", fail_asset_metrics_write)

    with pytest.raises(RuntimeError, match="simulated write failure"):
        write_analysis_database(db, tables)

    with sqlite3.connect(db) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        preserved = connection.execute("SELECT label FROM preserved").fetchone()[0]

    assert names == {"preserved"}
    assert preserved == "original"


def test_labeled_analysis_queries_return_expected_analysis_results(tmp_path):
    db = tmp_path / "analysis.sqlite"
    tables = {
        "prices": pd.DataFrame(
            {
                "symbol": ["A", "A", "A", "A", "B", "B", "C", "C"],
                "date": [
                    "2026-01-02",
                    "2026-01-30",
                    "2026-02-27",
                    "2026-02-27",
                    "2026-01-30",
                    "2026-02-27",
                    "2026-01-02",
                    "2026-02-27",
                ],
                "close": [100.0, 110.0, 121.0, 121.0, 50.0, 55.0, 100.0, 90.0],
            }
        ),
        "asset_metrics": pd.DataFrame(
            {
                "symbol": ["A", "B", "C"],
                "annualized_return": [0.25, 0.10, -0.05],
                "annualized_volatility": [0.20, 0.10, 0.30],
            }
        ),
        "portfolio_metrics": pd.DataFrame(
            {"portfolio": ["equal_weight"], "max_drawdown": [-0.1]}
        ),
        "portfolio_weights": pd.DataFrame(
            {
                "portfolio": ["equal_weight", "equal_weight"],
                "symbol": ["A", "B"],
                "weight": [0.5, 0.5],
            }
        ),
    }
    query_path = Path(__file__).parents[1] / "sql" / "analysis_queries.sql"

    write_analysis_database(db, tables)
    queries = _labeled_sql_statements(query_path)

    assert {label for label, _ in queries} == {
        "Monthly Returns",
        "Period Performance by Asset",
        "Annualized Volatility Ranking",
        "Missing and Duplicate Date Checks",
    }
    with sqlite3.connect(db) as connection:
        results = {
            label: connection.execute(statement).fetchall()
            for label, statement in queries
        }

    assert results["Monthly Returns"] == [
        ("A", "2026-01-30", 110.0, None),
        ("A", "2026-02-27", 121.0, pytest.approx(0.10)),
        ("B", "2026-01-30", 50.0, None),
        ("B", "2026-02-27", 55.0, pytest.approx(0.10)),
        ("C", "2026-01-02", 100.0, None),
        ("C", "2026-02-27", 90.0, pytest.approx(-0.10)),
    ]
    assert results["Period Performance by Asset"] == [
        ("A", "2026-01-02", "2026-02-27", 100.0, 121.0, pytest.approx(0.21)),
        ("B", "2026-01-30", "2026-02-27", 50.0, 55.0, pytest.approx(0.10)),
        ("C", "2026-01-02", "2026-02-27", 100.0, 90.0, pytest.approx(-0.10)),
    ]
    assert results["Annualized Volatility Ranking"] == [
        ("B", 0.10, 1),
        ("A", 0.20, 2),
        ("C", 0.30, 3),
    ]
    assert results["Missing and Duplicate Date Checks"] == [
        ("A", "2026-02-27", "duplicate", 1),
        ("C", "2026-01-30", "missing", 1),
    ]


def test_write_analysis_database_removes_temp_file_when_replace_fails(
    tmp_path, monkeypatch
):
    db = tmp_path / "analysis.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE preserved (label TEXT)")
        connection.execute("INSERT INTO preserved VALUES ('original')")
    tables = {
        "prices": pd.DataFrame(
            {"symbol": ["A"], "date": ["2026-01-02"], "close": [10.0]}
        ),
        "asset_metrics": pd.DataFrame({"symbol": ["A"]}),
        "portfolio_metrics": pd.DataFrame({"portfolio": ["equal_weight"]}),
        "portfolio_weights": pd.DataFrame(
            {"portfolio": ["equal_weight"], "symbol": ["A"], "weight": [1.0]}
        ),
    }

    def fail_replace(source, destination):
        raise PermissionError("simulated replacement failure")

    monkeypatch.setattr("portfolio_analysis.storage.os.replace", fail_replace)

    with pytest.raises(PermissionError, match="simulated replacement failure"):
        write_analysis_database(db, tables)

    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT label FROM preserved").fetchone()[0] == "original"
    assert not list(tmp_path.glob(".analysis.sqlite.*.tmp"))


def _labeled_sql_statements(path: Path) -> list[tuple[str, str]]:
    sections = re.split(r"^-- QUERY: (.+)$", path.read_text(encoding="utf-8"), flags=re.M)
    return list(zip(sections[1::2], sections[2::2]))
