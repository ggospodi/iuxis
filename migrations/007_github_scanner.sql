-- GitHub scanner integration
-- Adds fields to track GitHub repository sync status

-- Add GitHub-related columns to projects table
-- github_repo: full repo name (e.g., 'ggospodi/iuxis-dev')
-- github_last_scanned: timestamp of last successful scan
-- github_backfill_done: whether initial historical scan completed

-- Note: Using ALTER TABLE instead of direct column creation
-- Migration runner will handle IF NOT EXISTS logic
