"""Shared dependencies for FastAPI routes."""
import sqlite3
import os

def get_db():
    """Database connection dependency."""
    db_path = os.path.expanduser("~/Desktop/iuxis/data/iuxis.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
