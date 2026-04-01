#!/usr/bin/env python3
"""Safe migration runner. Handles SQLite's lack of ADD COLUMN IF NOT EXISTS."""
import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/iuxis.db")

def column_exists(conn, table, column):
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())

def run_migration_003(conn):
    print("Running migration 003: semantic memory...")

    cols_to_add = [
        ("importance",        "REAL DEFAULT 0.5"),
        ("pinned",            "BOOLEAN DEFAULT 0"),
        ("consolidated",      "BOOLEAN DEFAULT 0"),
        ("consolidated_into", "INTEGER"),
    ]
    for col_name, col_def in cols_to_add:
        if not column_exists(conn, "user_knowledge", col_name):
            conn.execute(f"ALTER TABLE user_knowledge ADD COLUMN {col_name} {col_def}")
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists: {col_name} (skipped)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS consolidation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            project_id INTEGER REFERENCES projects(id),
            entries_processed INTEGER,
            summary_entry_id INTEGER REFERENCES user_knowledge(id),
            trigger TEXT DEFAULT 'scheduled'
        )
    """)

    conn.execute("""
        UPDATE user_knowledge SET importance =
            CASE category
                WHEN 'decision'      THEN 0.85
                WHEN 'architecture'  THEN 0.83
                WHEN 'compliance'    THEN 0.80
                WHEN 'risk'          THEN 0.75
                WHEN 'fact'          THEN 0.70
                WHEN 'metric'        THEN 0.68
                WHEN 'relationship'  THEN 0.55
                ELSE 0.50
            END
        WHERE importance = 0.5 OR importance IS NULL
    """)

    conn.commit()
    print("Migration 003 complete.")

def run_migration_004(conn):
    print("Running migration 004: connectors...")
    migration_path = os.path.join(os.path.dirname(__file__), "004_connectors.sql")

    with open(migration_path, 'r') as f:
        sql = f.read()

    # Execute the entire migration file
    # SQLite executescript() automatically commits
    conn.executescript(sql)
    print("Migration 004 complete.")

def run_migration_005(conn):
    print("Running migration 005: retrieval layer...")

    # Add columns to user_knowledge
    cols_to_add = [
        ("validity_status", "TEXT NOT NULL DEFAULT 'current'"),
        ("superseded_by",   "INTEGER REFERENCES user_knowledge(id)"),
        ("supersedes",      "INTEGER REFERENCES user_knowledge(id)"),
        ("memory_tier",     "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col_name, col_def in cols_to_add:
        if not column_exists(conn, "user_knowledge", col_name):
            conn.execute(f"ALTER TABLE user_knowledge ADD COLUMN {col_name} {col_def}")
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists: {col_name} (skipped)")

    # Create new tables (these use IF NOT EXISTS so safe to run multiple times)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
            entity_type TEXT NOT NULL,
            entity_value TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'subject',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_entry ON knowledge_entities(entry_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type_value ON knowledge_entities(entity_type, entity_value)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_value ON knowledge_entities(entity_value)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_entry_id INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
            target_entry_id INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            detected_by TEXT NOT NULL DEFAULT 'extractor',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_source ON knowledge_relations(source_entry_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_target ON knowledge_relations(target_entry_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_type ON knowledge_relations(relation_type)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_value TEXT NOT NULL,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            current_state TEXT NOT NULL DEFAULT 'unknown',
            current_summary TEXT,
            confidence REAL DEFAULT 1.0,
            last_entry_id INTEGER REFERENCES user_knowledge(id),
            last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            state_history JSON NOT NULL DEFAULT '[]',
            UNIQUE(entity_type, entity_value, project_id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_states_lookup ON entity_states(entity_type, entity_value)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_states_project ON entity_states(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_states_updated ON entity_states(last_updated_at DESC)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS contradiction_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id_a INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
            entry_id_b INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
            similarity_score REAL NOT NULL,
            conflict_type TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            resolved_by_entry_id INTEGER REFERENCES user_knowledge(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_contradictions_pending ON contradiction_flags(status, created_at DESC)")

    # Backfill default values
    conn.execute("UPDATE user_knowledge SET memory_tier = 0 WHERE memory_tier IS NULL")
    conn.execute("UPDATE user_knowledge SET validity_status = 'current' WHERE validity_status IS NULL")

    conn.commit()
    print("Migration 005 complete.")

def run_migration_006(conn):
    print("Running migration 006: knowledge relations indexes...")
    migration_path = os.path.join(os.path.dirname(__file__), "006_knowledge_relations_index.sql")

    with open(migration_path, 'r') as f:
        sql = f.read()

    # Execute the entire migration file
    conn.executescript(sql)
    print("Migration 006 complete.")

def run_migration_007(conn):
    print("Running migration 007: github scanner...")

    cols_to_add = [
        ("github_repo",           "TEXT"),
        ("github_last_scanned",   "TIMESTAMP"),
        ("github_backfill_done",  "BOOLEAN DEFAULT 0"),
    ]
    for col_name, col_def in cols_to_add:
        if not column_exists(conn, "projects", col_name):
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_def}")
            print(f"  Added column: {col_name}")
        else:
            print(f"  Column already exists: {col_name} (skipped)")

    conn.commit()
    print("Migration 007 complete.")

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    run_migration_003(conn)
    run_migration_004(conn)
    run_migration_005(conn)
    run_migration_006(conn)
    run_migration_007(conn)
    conn.close()
