"""
relation_extractor.py - Knowledge Graph Relation Extraction

Analyzes knowledge entries to discover and extract semantic relationships
between them, building a queryable knowledge graph.
"""

import json
import logging
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from iuxis.llm_client import LLMClient

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "iuxis.db"

# Valid relationship types
VALID_RELATION_TYPES = {
    "causes", "blocks", "enables", "depends_on",
    "contradicts", "supersedes", "references", "supports"
}


def batch_extract_all_relations():
    """
    Full pass extraction - processes all valid knowledge entries and extracts relations.
    Groups entries by project and compares each entry with a sliding window of context.
    """
    logger.info("[RelationExtractor] Starting batch extraction...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch all valid entries grouped by project
    cursor.execute("""
        SELECT id, project_id, content, category, importance, created_at
        FROM user_knowledge
        WHERE validity_status = 'current' AND importance >= 0.3 AND source != 'github'
        ORDER BY project_id, created_at ASC
    """)
    all_entries = cursor.fetchall()

    if not all_entries:
        logger.info("[RelationExtractor] No valid entries found to process.")
        conn.close()
        return

    # Group entries by project
    entries_by_project: Dict[int, List] = defaultdict(list)
    for entry in all_entries:
        proj_id = entry["project_id"] if entry["project_id"] else 0
        entries_by_project[proj_id].append(entry)

    logger.info(f"[RelationExtractor] Found {len(all_entries)} entries across {len(entries_by_project)} projects")

    # Track statistics
    relation_counts = defaultdict(int)
    total_comparisons = 0

    # Process each project
    for project_id, entries in entries_by_project.items():
        project_name = _get_project_name(cursor, project_id)
        logger.info(f"[RelationExtractor] Processing project: {project_name} ({len(entries)} entries)")

        # Get entries from other projects for cross-project comparison
        other_entries = []
        for other_proj_id, other_proj_entries in entries_by_project.items():
            if other_proj_id != project_id:
                other_entries.extend(other_proj_entries)

        # Process each entry in this project
        for idx, entry in enumerate(entries, 1):
            if idx % 5 == 0:
                logger.info(f"  Project {project_name}: comparing entry {idx}/{len(entries)}...")

            # Build sliding window context
            # Last 10 from same project (excluding current entry)
            same_project_window = [e for e in entries if e["id"] != entry["id"]][-10:]

            # Last 5 from other projects
            other_project_window = other_entries[-5:]

            # Combine window
            comparison_window = same_project_window + other_project_window

            # Extract relations for this entry
            for target_entry in comparison_window:
                if entry["id"] == target_entry["id"]:
                    continue

                relation = _extract_relation_between(
                    cursor,
                    entry["id"], entry["content"], entry["category"],
                    target_entry["id"], target_entry["content"], target_entry["category"]
                )

                if relation:
                    relation_counts[relation["type"]] += 1

                total_comparisons += 1

    conn.close()

    # Print summary
    logger.info(f"\n[RelationExtractor] Batch extraction complete!")
    logger.info(f"  Total comparisons: {total_comparisons}")
    logger.info(f"  Relations found by type:")
    for rel_type, count in sorted(relation_counts.items()):
        logger.info(f"    {rel_type}: {count}")


def extract_relations_for_entry(entry_id: int, project_id: int):
    """
    Incremental extraction hook - processes a single new entry.
    Compares it against recent entries from the same and other projects.

    Args:
        entry_id: ID of the new entry to process
        project_id: Project ID the entry belongs to
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch the new entry
    cursor.execute("""
        SELECT id, content, category
        FROM user_knowledge
        WHERE id = ?
    """, (entry_id,))
    entry = cursor.fetchone()

    if not entry:
        logger.warning(f"[RelationExtractor] Entry {entry_id} not found")
        conn.close()
        return

    # Get last 10 entries from same project (excluding current)
    cursor.execute("""
        SELECT id, content, category
        FROM user_knowledge
        WHERE project_id = ? AND id != ? AND validity_status = 'current' AND importance >= 0.3
        ORDER BY created_at DESC
        LIMIT 10
    """, (project_id, entry_id))
    same_project_entries = cursor.fetchall()

    # Get last 5 entries from other projects
    cursor.execute("""
        SELECT id, content, category
        FROM user_knowledge
        WHERE project_id != ? AND validity_status = 'current' AND importance >= 0.3
        ORDER BY created_at DESC
        LIMIT 5
    """, (project_id,))
    other_project_entries = cursor.fetchall()

    # Combine comparison window
    comparison_window = list(same_project_entries) + list(other_project_entries)

    logger.info(f"[RelationExtractor] Extracting relations for entry {entry_id} against {len(comparison_window)} entries")

    # Extract relations
    for target_entry in comparison_window:
        _extract_relation_between(
            cursor,
            entry["id"], entry["content"], entry["category"],
            target_entry["id"], target_entry["content"], target_entry["category"]
        )

    conn.close()


def _extract_relation_between(
    cursor,
    from_id: int, from_content: str, from_category: str,
    to_id: int, to_content: str, to_category: str
) -> Optional[Dict]:
    """
    Use LLM to determine if a relation exists between two entries.

    Returns:
        Dict with relation info if found, None otherwise
    """
    llm = LLMClient()

    # Build prompt
    system_prompt = """You are a knowledge graph relation extractor. Analyze two knowledge entries and determine if there is a semantic relationship between them.

Valid relationship types:
- causes: A causes or leads to B
- blocks: A blocks or prevents B
- enables: A enables or makes B possible
- depends_on: A depends on B
- contradicts: A contradicts or conflicts with B
- supersedes: A supersedes or replaces B
- references: A references or mentions B
- supports: A supports or reinforces B

Output ONLY a JSON object with this structure:
{
  "has_relation": true or false,
  "type": "relationship_type",
  "confidence": "high", "medium", or "low"
}

If no clear relationship exists, return: {"has_relation": false}"""

    prompt = f"""Entry A ({from_category}):
{from_content[:500]}

Entry B ({to_category}):
{to_content[:500]}

Analyze if Entry A has a relationship to Entry B. Output JSON only."""

    # Retry logic with backoff
    for attempt in range(3):
        try:
            response = llm.generate_fast(prompt, system_prompt=system_prompt, format_json=True)
            result = LLMClient.parse_json_response(response, fallback={"has_relation": False})

            # Validate response
            if not result.get("has_relation", False):
                return None

            rel_type = result.get("type", "").strip()
            confidence = result.get("confidence", "low").strip()

            # Validate relation type
            if rel_type not in VALID_RELATION_TYPES:
                logger.warning(f"[RelationExtractor] Invalid relation type: {rel_type}")
                return None

            # Post-filter: drop 'references' unless high confidence
            if rel_type == "references" and confidence != "high":
                return None

            # Insert into database (INSERT OR IGNORE to handle duplicates)
            cursor.execute("""
                INSERT OR IGNORE INTO knowledge_relations
                (source_entry_id, target_entry_id, relation_type, confidence, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (from_id, to_id, rel_type, confidence))
            cursor.connection.commit()

            return {
                "from_id": from_id,
                "to_id": to_id,
                "type": rel_type,
                "confidence": confidence
            }

        except Exception as e:
            logger.warning(f"[RelationExtractor] Attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2)  # 2s backoff
            else:
                logger.error(f"[RelationExtractor] Failed to extract relation after 3 attempts")
                return None


def _get_project_name(cursor, project_id: int) -> str:
    """Get project name by ID."""
    if project_id == 0:
        return "None"

    cursor.execute("SELECT name FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    return row["name"] if row else f"Project-{project_id}"
