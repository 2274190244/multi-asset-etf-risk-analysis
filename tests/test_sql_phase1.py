import sqlite3
from pathlib import Path

def test_month_gap_is_not_one_month_return():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE prices(symbol TEXT,date TEXT,close REAL)")
    connection.executemany("INSERT INTO prices VALUES(?,?,?)", [
        ("A","2026-01-30",100), ("A","2026-03-31",121)])
    sql = Path("sql/analysis_queries.sql").read_text().split("-- QUERY: Period Performance by Asset")[0]
    rows = connection.execute(sql).fetchall()
    connection.close()
    assert rows[1][-1] is None
