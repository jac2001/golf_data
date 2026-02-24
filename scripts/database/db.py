"""
DuckDB connection helper.
Usage:
    from scripts.database.db import get_conn
    with get_conn() as conn:
        df = conn.execute("SELECT * FROM players").df()
"""
import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "golf_data.db"


def get_conn(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection to the golf database."""
    return duckdb.connect(str(DB_PATH), read_only=read_only)
