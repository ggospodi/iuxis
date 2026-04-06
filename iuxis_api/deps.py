"""Shared dependencies for FastAPI routes."""
import sqlite3
from iuxis.db import get_db_path

def get_db():
    """Database connection dependency — thread-safe for FastAPI."""
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = None
    try:
        yield conn
    finally:
        conn.close()
