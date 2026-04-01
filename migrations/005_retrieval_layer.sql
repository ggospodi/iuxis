-- ============================================================
-- Migration 005: Retrieval Architecture Layer
-- Adds entity graph, temporal state tracking, and validity
-- lifecycle to the knowledge base.
-- ============================================================

-- Validity and temporal decay columns on existing knowledge entries
-- validity_status tracks the knowledge lifecycle:
--   'current'    = active, should be retrieved by default
--   'superseded' = replaced by a newer entry (linked via superseded_by)
--   'historical' = old but intentionally preserved for context
--   'deprecated' = explicitly marked as no longer applicable
ALTER TABLE user_knowledge ADD COLUMN IF NOT EXISTS
    validity_status TEXT NOT NULL DEFAULT 'current';

ALTER TABLE user_knowledge ADD COLUMN IF NOT EXISTS
    superseded_by INTEGER REFERENCES user_knowledge(id);

ALTER TABLE user_knowledge ADD COLUMN IF NOT EXISTS
    supersedes INTEGER REFERENCES user_knowledge(id);

-- Temporal tier for hierarchical retrieval
-- 0=live (recent raw entry), 1=session summary, 2=project state, 3=archive
ALTER TABLE user_knowledge ADD COLUMN IF NOT EXISTS
    memory_tier INTEGER NOT NULL DEFAULT 0;

-- ============================================================
-- Entity index: what entities appear in each knowledge entry
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,   -- 'project', 'technology', 'person', 'decision_subject', 'constraint'
    entity_value TEXT NOT NULL,  -- normalized: lowercase, trimmed, e.g. 'aws nitro enclaves'
    role TEXT NOT NULL DEFAULT 'subject',  -- 'subject', 'object', 'context'
    confidence REAL NOT NULL DEFAULT 1.0,  -- 0.0–1.0, lower for inferred entities
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entities_entry ON knowledge_entities(entry_id);
CREATE INDEX IF NOT EXISTS idx_entities_type_value ON knowledge_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_entities_value ON knowledge_entities(entity_value);

-- ============================================================
-- Relation index: causal/temporal links between entries
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entry_id INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
    target_entry_id INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    -- relation_type values:
    --   'supersedes'   = source replaces target (target becomes superseded)
    --   'caused_by'    = source decision was caused by target context
    --   'enables'      = source creates a capability that enables target
    --   'contradicts'  = source and target state conflicting things
    --   'references'   = source cites or elaborates on target
    --   'follows'      = source is a temporal continuation of target
    confidence REAL NOT NULL DEFAULT 1.0,
    detected_by TEXT NOT NULL DEFAULT 'extractor',  -- 'extractor', 'user', 'llm'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_relations_source ON knowledge_relations(source_entry_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON knowledge_relations(target_entry_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON knowledge_relations(relation_type);

-- ============================================================
-- Entity state: current known state per tracked entity
-- This is the fast-lookup layer — avoids retrieval to know
-- the current status of anything Iuxis tracks.
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,

    -- Current state
    current_state TEXT NOT NULL DEFAULT 'unknown',
    -- current_state values vary by entity_type:
    --   project:           'active', 'paused', 'blocked', 'complete'
    --   technology:        'adopted', 'evaluating', 'rejected', 'deprecated'
    --   decision_subject:  'decided', 'open', 'reversed', 'superseded'
    --   person:            'active', 'departed', 'prospect'
    --   constraint:        'active', 'resolved', 'workaround'

    current_summary TEXT,        -- 300-token compressed current state, used in Tier 2 retrieval
    confidence REAL DEFAULT 1.0, -- how confident we are this is still current

    -- Tracking
    last_entry_id INTEGER REFERENCES user_knowledge(id),  -- most recent entry that updated this state
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- State history as JSON array: [{entry_id, state, summary, timestamp}, ...]
    state_history JSON NOT NULL DEFAULT '[]',

    UNIQUE(entity_type, entity_value, project_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_states_lookup ON entity_states(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_entity_states_project ON entity_states(project_id);
CREATE INDEX IF NOT EXISTS idx_entity_states_updated ON entity_states(last_updated_at DESC);

-- ============================================================
-- Contradiction log: pairs of entries flagged as potentially conflicting
-- Surfaced to user for resolution; not auto-resolved.
-- ============================================================
CREATE TABLE IF NOT EXISTS contradiction_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id_a INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
    entry_id_b INTEGER NOT NULL REFERENCES user_knowledge(id) ON DELETE CASCADE,
    similarity_score REAL NOT NULL,   -- cosine similarity between the two entries
    conflict_type TEXT,               -- 'decision_reversal', 'state_change', 'factual'
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'resolved', 'dismissed'
    resolved_by_entry_id INTEGER REFERENCES user_knowledge(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contradictions_pending ON contradiction_flags(status, created_at DESC);

-- ============================================================
-- Backfill: set memory_tier = 0 for all existing entries
-- (they are all raw entries as of this migration)
-- ============================================================
UPDATE user_knowledge SET memory_tier = 0 WHERE memory_tier IS NULL;
UPDATE user_knowledge SET validity_status = 'current' WHERE validity_status IS NULL;
