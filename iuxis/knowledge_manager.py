"""Knowledge manager — CRUD and search for the user_knowledge table.

This is Layer 2 of the ingestion architecture: the searchable knowledge base
where every extracted fact, decision, and context lives after ingestion.

Usage:
    from iuxis.knowledge_manager import (
        add_knowledge, search_knowledge, get_project_knowledge,
        get_knowledge_stats, archive_knowledge
    )
"""

import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict

from iuxis.db import get_connection, execute, fetch_all, fetch_one
from iuxis.embedder import Embedder
from iuxis.vector_store import VectorStore
from iuxis.importance import compute_importance
from iuxis.entity_extractor import extract_entities, write_entities, detect_supersession_relations
from iuxis.entity_state_manager import upsert_state

logger = logging.getLogger("iuxis.knowledge_manager")

# Module-level singletons for embedder and vector store
_embedder: Optional[Embedder] = None
_vector_store: Optional[VectorStore] = None


def _get_embedder() -> Embedder:
    """Get or initialize the embedder singleton."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def _get_vector_store() -> VectorStore:
    """Get or initialize the vector store singleton."""
    global _vector_store
    if _vector_store is None:
        embedder = _get_embedder()
        _vector_store = VectorStore(embed_dim=embedder.dim)
    return _vector_store


# ---------------------------------------------------------------------------
# Valid categories (superset of original schema CHECK + new ingestion types)
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    # Original schema categories
    "preference", "pattern", "decision", "fact", "project_context", "workflow_rule",
    # New ingestion categories
    "context", "relationship", "compliance", "risk", "metric", "contact", "timeline",
    # GitHub scanner
    "github_activity",
}

VALID_STATUSES = {"proposed", "approved", "rejected", "archived"}
VALID_CONFIDENCES = {"high", "medium", "low"}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def add_knowledge(
    category: str,
    content: str,
    source: str = "ingestion",
    project_id: Optional[int] = None,
    source_file: Optional[str] = None,
    confidence: str = "high",
    status: str = "approved",
    tags: Optional[list[str]] = None,
    pinned: bool = False,
) -> int:
    """Add a knowledge entry. Returns the new entry ID."""
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {VALID_CATEGORIES}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {VALID_STATUSES}")
    if confidence not in VALID_CONFIDENCES:
        raise ValueError(f"Invalid confidence '{confidence}'. Must be one of: {VALID_CONFIDENCES}")

    # Compute importance score
    importance = compute_importance(
        category=category,
        content=content,
        source=source,
        confidence=confidence,
        pinned=pinned,
    )

    tags_json = json.dumps(tags) if tags else None

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO user_knowledge
           (category, content, source, project_id, source_file, confidence, status, relevance_tags, importance, pinned)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (category, content, source, project_id, source_file, confidence, status, tags_json, importance, int(pinned)),
    )
    new_id = cursor.lastrowid
    conn.commit()

    # Add to vector store
    try:
        embedder = _get_embedder()
        vector_store = _get_vector_store()
        vec = embedder.embed(content)
        vector_store.add(entry_id=new_id, vector=vec)
        logger.info(f"[KnowledgeManager] Added entry {new_id} to vector store")
    except Exception as e:
        logger.warning(f"[KnowledgeManager] Vector indexing failed for entry {new_id}: {e}")

    # --- Entity extraction (Bet 3 retrieval layer) ---
    try:
        extraction = extract_entities(
            content=content,
            project_slug=None,  # we have project_id not slug here — pass None
            category=category,
        )
        write_entities(new_id, extraction)

        # Update entity states
        upsert_state(
            entry_id=new_id,
            project_id=project_id or 1,
            category=category,
            content=content,
            entities=extraction.entities,
        )

            # Detect and mark superseded entries
        if extraction.supersedes_values and project_id:
            detect_supersession_relations(
                new_entry_id=new_id,
                supersedes_values=extraction.supersedes_values,
                project_id=project_id,
            )
    except Exception as exc:
        # Entity extraction is non-critical — never block knowledge write
        logger.warning(f"[KnowledgeManager] Entity extraction failed for entry {new_id}: {exc}")

    # --- Relation extraction (KG agent) ---
    try:
        if project_id and source != "github":
            from iuxis.relation_extractor import extract_relations_for_entry
            extract_relations_for_entry(new_id, project_id)
    except Exception as exc:
        logger.warning(f"[KnowledgeManager] Relation extraction failed for entry {new_id}: {exc}")

    return new_id


def add_knowledge_batch(entries: list[dict], project_id: Optional[int] = None) -> int:
    """Add multiple knowledge entries at once. Returns count inserted."""
    conn = get_connection()
    count = 0
    new_ids = []
    for entry in entries:
        tags_json = json.dumps(entry.get("tags")) if entry.get("tags") else None
        cursor = conn.execute(
            """INSERT INTO user_knowledge
               (category, content, source, project_id, source_file, confidence, status, relevance_tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.get("category", "fact"),
                entry["content"],
                entry.get("source", "ingestion"),
                entry.get("project_id", project_id),
                entry.get("source_file"),
                entry.get("confidence", "high"),
                entry.get("status", "approved"),
                tags_json,
            ),
        )
        new_ids.append((cursor.lastrowid, entry.get("project_id", project_id)))
        count += 1
    conn.commit()

    # Extract relations for new entries
    try:
        from iuxis.relation_extractor import extract_relations_for_entry
        for entry_id, proj_id in new_ids:
            if proj_id:
                if entry.get("source") != "github":
                    extract_relations_for_entry(entry_id, proj_id)
    except Exception as e:
        logger.warning(f"[KnowledgeManager] Relation extraction failed: {e}")

    return count


# ---------------------------------------------------------------------------
# Read / Search
# ---------------------------------------------------------------------------

def get_knowledge(knowledge_id: int) -> Optional[dict]:
    """Get a single knowledge entry by ID."""
    row = fetch_one("SELECT * FROM user_knowledge WHERE id = ?", (knowledge_id,))
    return dict(row) if row else None


def get_project_knowledge(
    project_id: int,
    category: Optional[str] = None,
    status: str = "approved",
    limit: int = 50,
) -> list[dict]:
    """Get knowledge entries for a specific project."""
    query = "SELECT * FROM user_knowledge WHERE project_id = ? AND status = ?"
    params: list = [project_id, status]

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = fetch_all(query, tuple(params))
    return [dict(r) for r in rows]


def search_knowledge(
    query: str,
    project_id: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Search knowledge entries by content text match.
    
    Uses SQLite LIKE for now. Future: embeddings-based semantic search.
    """
    sql = "SELECT * FROM user_knowledge WHERE status = 'approved'"
    params: list = []

    # Split query into keywords and search for each
    keywords = query.strip().split()
    if keywords:
        keyword_clauses = []
        for kw in keywords:
            keyword_clauses.append("content LIKE ?")
            params.append(f"%{kw}%")
        sql += " AND (" + " AND ".join(keyword_clauses) + ")"

    if project_id:
        sql += " AND project_id = ?"
        params.append(project_id)

    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = fetch_all(sql, tuple(params))
    return [dict(r) for r in rows]


def get_cross_project_knowledge(limit: int = 20) -> list[dict]:
    """Get knowledge entries that span multiple projects (project_id IS NULL)."""
    rows = fetch_all(
        """SELECT * FROM user_knowledge 
           WHERE project_id IS NULL AND status = 'approved'
           ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Context Assembly Helpers
# ---------------------------------------------------------------------------

def get_knowledge_for_context(project_id: Optional[int] = None, limit: int = 15) -> str:
    """Get a formatted knowledge summary for inclusion in Claude context.
    
    Returns a text block suitable for the [PROJECT_KNOWLEDGE] section
    of the context assembler.
    """
    entries = []

    if project_id:
        # Project-specific knowledge
        rows = fetch_all(
            """SELECT category, content, created_at FROM user_knowledge
               WHERE project_id = ? AND status = 'approved'
               ORDER BY created_at DESC LIMIT ?""",
            (project_id, limit),
        )
        entries.extend(rows)

        # Also include cross-project knowledge
        cross = fetch_all(
            """SELECT category, content, created_at FROM user_knowledge
               WHERE project_id IS NULL AND status = 'approved'
               ORDER BY created_at DESC LIMIT 5""",
        )
        entries.extend(cross)
    else:
        # General context — most recent approved knowledge
        rows = fetch_all(
            """SELECT category, content, created_at FROM user_knowledge
               WHERE status = 'approved'
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        entries.extend(rows)

    if not entries:
        return "[PROJECT_KNOWLEDGE]\nNo knowledge entries yet."

    lines = ["[PROJECT_KNOWLEDGE]"]
    for e in entries:
        cat = e["category"].upper() if isinstance(e, dict) else e[0].upper()
        content = e["content"] if isinstance(e, dict) else e[1]
        lines.append(f"  [{cat}] {content}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Update / Archive
# ---------------------------------------------------------------------------

def update_knowledge(knowledge_id: int, **kwargs) -> bool:
    """Update a knowledge entry."""
    allowed = {"category", "content", "status", "confidence", "relevance_tags", "project_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    if "relevance_tags" in updates and isinstance(updates["relevance_tags"], list):
        updates["relevance_tags"] = json.dumps(updates["relevance_tags"])

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [knowledge_id]

    execute(
        f"UPDATE user_knowledge SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        tuple(values),
    )
    return True


def archive_knowledge(project_id: int, before_date: Optional[str] = None) -> int:
    """Archive old knowledge entries for a project. Returns count archived."""
    query = "UPDATE user_knowledge SET status = 'archived' WHERE project_id = ? AND status = 'approved'"
    params: list = [project_id]

    if before_date:
        query += " AND created_at < ?"
        params.append(before_date)

    conn = get_connection()
    cursor = conn.execute(query, tuple(params))
    conn.commit()
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_knowledge_stats() -> dict:
    """Get knowledge base statistics."""
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0]
    approved = conn.execute(
        "SELECT COUNT(*) FROM user_knowledge WHERE status = 'approved'"
    ).fetchone()[0]

    # Per-project counts
    project_counts = conn.execute(
        """SELECT p.name, COUNT(uk.id) as count
           FROM user_knowledge uk
           JOIN projects p ON uk.project_id = p.id
           WHERE uk.status = 'approved'
           GROUP BY uk.project_id
           ORDER BY count DESC"""
    ).fetchall()

    # Per-category counts
    category_counts = conn.execute(
        """SELECT category, COUNT(*) as count
           FROM user_knowledge
           WHERE status = 'approved'
           GROUP BY category
           ORDER BY count DESC"""
    ).fetchall()

    # Cross-project count
    cross_project = conn.execute(
        "SELECT COUNT(*) FROM user_knowledge WHERE project_id IS NULL AND status = 'approved'"
    ).fetchone()[0]

    return {
        "total": total,
        "approved": approved,
        "cross_project": cross_project,
        "by_project": [(row[0], row[1]) for row in project_counts],
        "by_category": [(row[0], row[1]) for row in category_counts],
    }


def format_stats(stats: dict) -> str:
    """Format stats dict as human-readable text."""
    lines = [
        f"📊 Knowledge Base: {stats['approved']} approved entries ({stats['total']} total)",
        "",
    ]

    if stats["by_project"]:
        lines.append("By project:")
        for name, count in stats["by_project"]:
            lines.append(f"  {name}: {count} entries")

    if stats["cross_project"]:
        lines.append(f"  Cross-project: {stats['cross_project']} entries")

    if stats["by_category"]:
        lines.append("\nBy category:")
        for cat, count in stats["by_category"]:
            lines.append(f"  {cat}: {count}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Semantic Memory & Hybrid Retrieval
# ---------------------------------------------------------------------------

def _fetch_by_ids(entry_ids: List[int]) -> List[dict]:
    """Fetch knowledge entries by their IDs."""
    if not entry_ids:
        return []
    placeholders = ",".join("?" * len(entry_ids))
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT id, category, content, source, confidence, importance, pinned, project_id, created_at
            FROM user_knowledge WHERE id IN ({placeholders})""",
        entry_ids
    ).fetchall()

    id_pos = {eid: i for i, eid in enumerate(entry_ids)}
    result = [
        {
            "id": r[0], "category": r[1], "content": r[2],
            "source": r[3], "confidence": r[4], "importance": r[5],
            "pinned": bool(r[6]), "project_id": r[7], "created_at": r[8]
        }
        for r in rows
    ]
    return sorted(result, key=lambda e: id_pos.get(e["id"], 999))


def search_semantic(query: str, topk: int = 10) -> List[dict]:
    """
    Semantic search over knowledge entries using vector similarity.
    Returns list of knowledge dicts sorted by relevance.
    """
    embedder = _get_embedder()
    vector_store = _get_vector_store()

    query_vec = embedder.embed(query)
    hits = vector_store.search(query_vec, topk=topk)
    if not hits:
        return []

    entry_ids = [entry_id for entry_id, _ in hits]
    score_map = {entry_id: score for entry_id, score in hits}

    entries = _fetch_by_ids(entry_ids)
    # Attach semantic score
    for entry in entries:
        entry["semantic_score"] = score_map.get(entry["id"], 0.0)

    return sorted(entries, key=lambda e: e["semantic_score"], reverse=True)


def search_hybrid(query: str, project_id: Optional[int] = None, topk: int = 12) -> List[dict]:
    """
    Hybrid retrieval: semantic results + project-scoped SQL results, merged and
    importance-ranked. Used by context_assembler for all LLM context assembly.
    """
    # Semantic path
    semantic = search_semantic(query, topk=topk)
    semantic_ids = {e["id"] for e in semantic}

    # SQL path (existing — recency + project filter)
    sql_entries = get_project_knowledge(project_id=project_id, limit=20) if project_id else []

    # Merge: semantic first, then SQL entries not already included
    merged = list(semantic)
    for entry in sql_entries:
        if entry["id"] not in semantic_ids:
            entry["semantic_score"] = 0.0
            merged.append(entry)

    # Re-rank by combined score: importance (0.6 weight) + semantic (0.4 weight)
    for entry in merged:
        entry["_rank_score"] = (
            0.6 * entry.get("importance", 0.5) +
            0.4 * entry.get("semantic_score", 0.0)
        )

    return sorted(merged, key=lambda e: e["_rank_score"], reverse=True)[:topk]


def _fetch_all_for_indexing() -> List[Dict]:
    """Fetch all knowledge entries for vector index rebuild."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, content FROM user_knowledge WHERE content IS NOT NULL AND content != ''"
    ).fetchall()
    return [{"id": row[0], "content": row[1]} for row in rows]


def rebuild_vector_index():
    """Rebuild FAISS index from all existing knowledge entries. Call on startup if needed."""
    embedder = _get_embedder()
    vector_store = _get_vector_store()
    entries = _fetch_all_for_indexing()
    vector_store.rebuild(entries, embedder.embed)
    logger.info(f"[KnowledgeManager] Vector index rebuilt: {vector_store.total} entries")


def pin_entry(entry_id: int) -> bool:
    """Pin a knowledge entry — sets pinned=True and recomputes importance."""
    conn = get_connection()
    row = conn.execute(
        "SELECT category, content, source, confidence FROM user_knowledge WHERE id = ?",
        (entry_id,)
    ).fetchone()
    if not row:
        return False

    new_importance = compute_importance(
        category=row[0], content=row[1], source=row[2],
        confidence=row[3], pinned=True
    )
    conn.execute(
        "UPDATE user_knowledge SET pinned = 1, importance = ? WHERE id = ?",
        (new_importance, entry_id)
    )
    conn.commit()
    return True


def get_vector_store_total() -> int:
    """Return the total number of entries in the vector store."""
    vector_store = _get_vector_store()
    return vector_store.total
