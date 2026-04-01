"""SQLite database connection, schema initialization, and query helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Generator

import yaml

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

_CONFIG: Optional[dict] = None


def load_config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path) as f:
            _CONFIG = yaml.safe_load(f)
    return _CONFIG


def get_db_path() -> Path:
    cfg = load_config()
    db_rel = cfg.get("database", {}).get("path", "data/iuxis.db")
    return Path(__file__).parent.parent / db_rel


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a new SQLite connection with row_factory set."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_session(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that commits on success, rolls back on error."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER REFERENCES projects(id),
    name TEXT NOT NULL UNIQUE,
    type TEXT CHECK(type IN ('company','product','research','learning','advisory','consulting')),
    status TEXT DEFAULT 'active' CHECK(status IN ('active','paused','blocked','monitoring')),
    priority INTEGER DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    description TEXT,
    time_allocation_hrs_week REAL DEFAULT 0,
    current_focus TEXT,
    obsidian_folder TEXT,
    tags TEXT DEFAULT '[]',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'todo' CHECK(status IN ('todo','in_progress','blocked','done','cancelled')),
    priority INTEGER DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    due_date DATE,
    estimated_hours REAL,
    actual_hours REAL DEFAULT 0,
    created_by TEXT DEFAULT 'user' CHECK(created_by IN ('user','ai')),
    ai_rationale TEXT,
    tags TEXT DEFAULT '[]',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

-- Schedule blocks
CREATE TABLE IF NOT EXISTS schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    task_id INTEGER REFERENCES tasks(id),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    block_type TEXT DEFAULT 'deep_work' CHECK(block_type IN ('deep_work','admin','meeting','break','review')),
    status TEXT DEFAULT 'planned' CHECK(status IN ('planned','active','completed','skipped')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- AI insights
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT CHECK(type IN ('priority','dependency','pattern','recommendation','alert','coaching')),
    content TEXT NOT NULL,
    related_project_ids TEXT DEFAULT '[]',
    related_task_ids TEXT DEFAULT '[]',
    severity TEXT DEFAULT 'info' CHECK(severity IN ('info','warning','action_required')),
    status TEXT DEFAULT 'new' CHECK(status IN ('new','seen','acted_on','dismissed')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge base
CREATE TABLE IF NOT EXISTS user_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id),
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    source_file TEXT,
    confidence TEXT DEFAULT 'high',
    status TEXT DEFAULT 'proposed',
    relevance_tags TEXT,
    last_used_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_project ON user_knowledge(project_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON user_knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_status ON user_knowledge(status);

-- Chat channels
CREATE TABLE IF NOT EXISTS chat_channels (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    channel_type TEXT CHECK(channel_type IN ('general', 'project', 'custom'))
);

-- Chat history
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Activity log
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT CHECK(event_type IN (
        'task_created','task_completed','task_status_change',
        'project_priority_change','schedule_block_completed','schedule_block_skipped',
        'insight_generated','chat_query','obsidian_pull'
    )),
    details TEXT,
    project_id INTEGER REFERENCES projects(id),
    task_id INTEGER REFERENCES tasks(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Obsidian vault index
CREATE TABLE IF NOT EXISTS vault_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    file_type TEXT,
    frontmatter TEXT DEFAULT '{}',
    tags TEXT DEFAULT '[]',
    last_modified DATETIME,
    indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Configuration store
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule_blocks(date);
CREATE INDEX IF NOT EXISTS idx_insights_status ON insights(status);
CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log(event_type);
CREATE INDEX IF NOT EXISTS idx_vault_path ON vault_index(file_path);
CREATE INDEX IF NOT EXISTS idx_projects_parent ON projects(parent_id);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    """Create all tables if they don't exist."""
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
    print(f"✓ Database initialized at {db_path or get_db_path()}")


# ---------------------------------------------------------------------------
# Generic query helpers
# ---------------------------------------------------------------------------

def fetch_all(query: str, params: tuple = (), db_path: Optional[Path] = None) -> list[dict]:
    with db_session(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def fetch_one(query: str, params: tuple = (), db_path: Optional[Path] = None) -> Optional[dict]:
    with db_session(db_path) as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def execute(query: str, params: tuple = (), db_path: Optional[Path] = None) -> int:
    """Execute a write query and return lastrowid."""
    with db_session(db_path) as conn:
        cursor = conn.execute(query, params)
        return cursor.lastrowid


def log_activity(
    event_type: str,
    details: str = "",
    project_id: Optional[int] = None,
    task_id: Optional[int] = None,
) -> None:
    """Write to the activity log."""
    execute(
        "INSERT INTO activity_log (event_type, details, project_id, task_id) VALUES (?, ?, ?, ?)",
        (event_type, details, project_id, task_id),
    )
