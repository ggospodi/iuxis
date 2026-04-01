-- Migration 006: Knowledge Relations Indexes
-- Adds indexes to optimize knowledge_relations queries

CREATE UNIQUE INDEX IF NOT EXISTS idx_kr_unique ON knowledge_relations(source_entry_id, target_entry_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_kr_from ON knowledge_relations(source_entry_id);
CREATE INDEX IF NOT EXISTS idx_kr_to ON knowledge_relations(target_entry_id);
