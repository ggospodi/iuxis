"""
Entity extractor for Iuxis knowledge entries.

Runs at write time (inside knowledge_manager.add_knowledge()).
Extracts structured entities and detects potential relations
using pattern matching — no LLM call required.

Extracted entity types:
  - project:            known project names/slugs
  - technology:         tech stack terms (AWS, FAISS, FastAPI, etc.)
  - person:             proper names in context of roles/relationships
  - decision_subject:   what a decision is about ("decided to use X")
  - constraint:         blockers, dependencies, limitations

Detected relations:
  - supersedes:         "replaced X", "switched from X", "no longer using X"
  - contradicts:        detected via similarity check against existing entries
  - follows:            temporal continuation within same project+category
"""

import re
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# Entity vocabulary — add new terms here as the project grows
# ============================================================

# Project names and their aliases → canonical slug
PROJECT_ALIASES = {
    "novabrew": "novabrew",
    "nova brew": "novabrew",
    "orbit marketing": "orbit-marketing",
    "orbit": "orbit-marketing",
    "iuxis": "iuxis",
}

# Technology terms to extract
TECHNOLOGY_TERMS = {
    # Infrastructure
    "aws", "aws nitro enclaves", "nitro enclaves", "s3", "ec2", "vpc", "kms",
    "terraform", "docker", "kubernetes",
    # AI/ML
    "faiss", "ollama", "deepseek", "qwen", "lm studio", "nomic-embed-text",
    "vector store", "embeddings", "rag", "semantic search",
    # Stack
    "fastapi", "sqlite", "next.js", "react", "tailwind", "framer motion",
    "playwright", "apscheduler", "uvicorn", "pydantic",
    "stripe", "lemon squeezy",
    # Concepts
    "nitro enclave", "tee", "trusted execution environment", "hipaa",
    "cryptographic proof", "zero trust", "local-first",
}

# Patterns that indicate a decision is being recorded
DECISION_PATTERNS = [
    r"decided?\s+to\s+(?:use|build|adopt|implement|go\s+with|pursue)\s+([a-zA-Z0-9\s\-_]+)",
    r"choosing\s+([a-zA-Z0-9\s\-_]+)\s+(?:over|instead\s+of|rather\s+than)",
    r"will\s+use\s+([a-zA-Z0-9\s\-_]+)\s+(?:for|as|to)",
    r"switched?\s+(?:from\s+\S+\s+)?to\s+([a-zA-Z0-9\s\-_]+)",
    r"going\s+with\s+([a-zA-Z0-9\s\-_]+)",
    r"selected\s+([a-zA-Z0-9\s\-_]+)\s+as",
]

# Patterns indicating supersession / reversal
SUPERSESSION_PATTERNS = [
    r"(?:no\s+longer|not\s+using|abandoned|dropped|removed|replaced)\s+([a-zA-Z0-9\s\-_]+)",
    r"switched?\s+from\s+([a-zA-Z0-9\s\-_]+)",
    r"moved?\s+away\s+from\s+([a-zA-Z0-9\s\-_]+)",
    r"deprecated\s+([a-zA-Z0-9\s\-_]+)",
    r"([a-zA-Z0-9\s\-_]+)\s+is\s+deprecated",
    r"reverting\s+(?:from\s+)?([a-zA-Z0-9\s\-_]+)",
]

# Patterns indicating constraints or blockers
CONSTRAINT_PATTERNS = [
    r"blocked\s+by\s+([^.]+)",
    r"requires?\s+([^.]+?)\s+(?:before|first|to\s+proceed)",
    r"depends?\s+on\s+([^.]+)",
    r"waiting\s+(?:on|for)\s+([^.]+)",
    r"constraint[:\s]+([^.]+)",
    r"limitation[:\s]+([^.]+)",
]


@dataclass
class ExtractedEntity:
    entity_type: str
    entity_value: str
    role: str = "subject"
    confidence: float = 1.0


@dataclass
class ExtractionResult:
    entities: list = field(default_factory=list)
    supersedes_values: list = field(default_factory=list)  # technology values this entry supersedes
    has_decision: bool = False
    has_constraint: bool = False


def _normalize(text: str) -> str:
    """Lowercase, strip extra whitespace."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def extract_entities(
    content: str,
    project_slug: Optional[str] = None,
    category: Optional[str] = None,
) -> ExtractionResult:
    """
    Extract entities from knowledge entry content.

    Args:
        content:      The knowledge entry text
        project_slug: Optional hint — the project this entry belongs to
        category:     Optional hint — 'decision', 'architecture', 'context', etc.

    Returns:
        ExtractionResult with entities list and metadata
    """
    result = ExtractionResult()
    normalized = _normalize(content)

    # --- Project entities ---
    for alias, slug in PROJECT_ALIASES.items():
        if alias in normalized:
            result.entities.append(ExtractedEntity(
                entity_type="project",
                entity_value=slug,
                role="subject" if slug == project_slug else "context",
                confidence=0.95,
            ))

    # --- Technology entities ---
    # Sort by length descending to match longer terms first
    for term in sorted(TECHNOLOGY_TERMS, key=len, reverse=True):
        if term in normalized:
            result.entities.append(ExtractedEntity(
                entity_type="technology",
                entity_value=term,
                role="subject",
                confidence=0.9,
            ))

    # --- Decision subjects ---
    if category == "decision" or "decided" in normalized or "decision" in normalized:
        result.has_decision = True
        for pattern in DECISION_PATTERNS:
            matches = re.findall(pattern, normalized, re.IGNORECASE)
            for match in matches:
                subject = match.strip()[:60]  # cap length
                if len(subject) > 2:
                    result.entities.append(ExtractedEntity(
                        entity_type="decision_subject",
                        entity_value=subject,
                        role="subject",
                        confidence=0.85,
                    ))

    # --- Supersession signals ---
    for pattern in SUPERSESSION_PATTERNS:
        matches = re.findall(pattern, normalized, re.IGNORECASE)
        for match in matches:
            value = match.strip()[:60]
            if len(value) > 2:
                result.supersedes_values.append(value)
                result.entities.append(ExtractedEntity(
                    entity_type="technology",
                    entity_value=value,
                    role="object",  # being superseded
                    confidence=0.8,
                ))

    # --- Constraint entities ---
    for pattern in CONSTRAINT_PATTERNS:
        matches = re.findall(pattern, normalized, re.IGNORECASE)
        if matches:
            result.has_constraint = True
            for match in matches:
                constraint = match.strip()[:80]
                if len(constraint) > 5:
                    result.entities.append(ExtractedEntity(
                        entity_type="constraint",
                        entity_value=constraint,
                        role="subject",
                        confidence=0.75,
                    ))

    # Deduplicate entities by (type, value)
    seen = set()
    deduped = []
    for e in result.entities:
        key = (e.entity_type, e.entity_value)
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    result.entities = deduped

    return result


def write_entities(
    entry_id: int,
    result: ExtractionResult,
    db_path: str = "data/iuxis.db",
):
    """
    Persist extracted entities to knowledge_entities table.
    Called from knowledge_manager after extraction.
    """
    if not result.entities:
        return

    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        conn.executemany(
            """INSERT OR IGNORE INTO knowledge_entities
               (entry_id, entity_type, entity_value, role, confidence)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (entry_id, e.entity_type, e.entity_value, e.role, e.confidence)
                for e in result.entities
            ]
        )
        conn.commit()
    except Exception as exc:
        logger.warning(f"[EntityExtractor] write_entities failed for entry {entry_id}: {exc}")
    finally:
        conn.close()


def detect_supersession_relations(
    new_entry_id: int,
    supersedes_values: list,
    project_id: int,
    db_path: str = "data/iuxis.db",
) -> list:
    """
    For each superseded value, find existing entries that reference it
    and mark them as superseded. Returns list of entry_ids that were marked.

    Only marks entries within the same project to avoid cross-project pollution.
    """
    if not supersedes_values:
        return []

    marked = []
    conn = sqlite3.connect(db_path, check_same_thread=False)

    try:
        for value in supersedes_values:
            # Find existing entries in the same project that mention this value
            # and are currently 'current' validity
            rows = conn.execute(
                """SELECT uk.id FROM user_knowledge uk
                   JOIN knowledge_entities ke ON ke.entry_id = uk.id
                   WHERE ke.entity_value LIKE ?
                     AND uk.project_id = ?
                     AND uk.validity_status = 'current'
                     AND uk.id != ?
                   ORDER BY uk.created_at DESC""",
                [f"%{value}%", project_id, new_entry_id]
            ).fetchall()

            for (old_entry_id,) in rows:
                # Mark old entry as superseded
                conn.execute(
                    """UPDATE user_knowledge
                       SET validity_status = 'superseded', superseded_by = ?
                       WHERE id = ?""",
                    [new_entry_id, old_entry_id]
                )
                # Mark new entry as superseding
                conn.execute(
                    """UPDATE user_knowledge
                       SET supersedes = ?
                       WHERE id = ? AND supersedes IS NULL""",
                    [old_entry_id, new_entry_id]
                )
                # Create relation record
                conn.execute(
                    """INSERT OR IGNORE INTO knowledge_relations
                       (source_entry_id, target_entry_id, relation_type, detected_by)
                       VALUES (?, ?, 'supersedes', 'extractor')""",
                    [new_entry_id, old_entry_id]
                )
                marked.append(old_entry_id)
                logger.info(
                    f"[EntityExtractor] Entry {old_entry_id} superseded by {new_entry_id} "
                    f"(via '{value}')"
                )

        conn.commit()
    except Exception as exc:
        logger.warning(f"[EntityExtractor] supersession detection failed: {exc}")
    finally:
        conn.close()

    return marked
