-- Migration 003: Semantic memory layer
-- Run once. Safe to re-run (uses IF NOT EXISTS / column existence checks).

-- Add importance scoring columns to user_knowledge
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS directly, so use Python migration runner

ALTER TABLE user_knowledge ADD COLUMN importance REAL DEFAULT 0.5;
ALTER TABLE user_knowledge ADD COLUMN pinned BOOLEAN DEFAULT 0;
ALTER TABLE user_knowledge ADD COLUMN consolidated BOOLEAN DEFAULT 0;
ALTER TABLE user_knowledge ADD COLUMN consolidated_into INTEGER REFERENCES user_knowledge(id);

-- Consolidation audit table
CREATE TABLE IF NOT EXISTS consolidation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    entries_processed INTEGER,
    summary_entry_id INTEGER REFERENCES user_knowledge(id),
    trigger TEXT DEFAULT 'scheduled'
);

-- Backfill importance scores for existing entries based on category
UPDATE user_knowledge SET importance =
    CASE category
        WHEN 'decision'      THEN 0.85
        WHEN 'architecture'  THEN 0.83
        WHEN 'compliance'    THEN 0.80
        WHEN 'risk'          THEN 0.75
        WHEN 'fact'          THEN 0.70
        WHEN 'metric'        THEN 0.68
        WHEN 'relationship'  THEN 0.55
        WHEN 'context'       THEN 0.50
        ELSE 0.50
    END
WHERE importance = 0.5 OR importance IS NULL;
