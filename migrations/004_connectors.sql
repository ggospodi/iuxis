-- Connector registry: tracks authorized sync sources
CREATE TABLE IF NOT EXISTS sync_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT NOT NULL,           -- 'file_watcher', 'slack', 'notion', 'linear'
  project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  config JSON NOT NULL DEFAULT '{}',   -- source-specific config (paths, credentials)
  last_synced_at TIMESTAMP,
  sync_interval_minutes INTEGER DEFAULT 0,  -- 0 = event-driven, >0 = polling
  enabled BOOLEAN NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for every sync attempt
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER REFERENCES sync_sources(id),
  source_type TEXT NOT NULL,           -- denormalized for easy querying
  project_slug TEXT,                   -- which project was targeted
  filename TEXT,                       -- original filename processed
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP,
  entries_added INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running',  -- 'running', 'success', 'error', 'skipped'
  error_message TEXT,
  destination_path TEXT                -- where file was copied to
);

-- Index for fast recent-runs queries
CREATE INDEX IF NOT EXISTS idx_sync_runs_status ON sync_runs(status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_runs_project ON sync_runs(project_slug, started_at DESC);
