"""
Entity state manager.

Maintains the entity_states table — a fast-lookup record of the
current known state of every tracked entity in Iuxis.

This is the mechanism that prevents institutional hallucination:
instead of asking FAISS "what's the current state of X?", the
briefing engine queries entity_states directly for a fresh,
explicitly-maintained answer.

Key responsibilities:
  1. upsert_state()     — update entity state when a new knowledge entry lands
  2. get_project_states() — retrieve all current states for a project (for briefing)
  3. flag_stale_states()  — identify states not updated in N days despite project activity
  4. get_contradiction_pairs() — surface pending contradictions for user review
"""

import json
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# Maps knowledge category + entity type to a likely state value
STATE_INFERENCE = {
    # category → entity_type → content_hints → state
    "decision": {
        "technology": {
            "adopted|using|chose|selected|going with|decided to use": "adopted",
            "rejected|not using|abandoned|dropped|switched away": "rejected",
            "evaluating|testing|exploring|considering|investigating": "evaluating",
            "deprecated|no longer|removed": "deprecated",
        },
        "decision_subject": {
            "decided|resolved|confirmed|finalized": "decided",
            "reversed|changed|reconsidering|revisiting": "reversed",
            "open|unclear|undecided|pending": "open",
        },
    },
    "context": {
        "project": {
            "active|resumed|started|launched|running": "active",
            "paused|blocked|on hold|waiting|deferred": "paused",
            "complete|done|shipped|finished|closed": "complete",
        },
    },
    "architecture": {
        "technology": {
            "using|integrated|deployed|implemented|built with": "adopted",
            "replacing|migrating|moving away": "evaluating",
        },
    },
}


def _infer_state(category: str, entity_type: str, content: str) -> str:
    """
    Infer likely state from content keywords.
    Returns 'unknown' if no clear signal found.
    """
    content_lower = content.lower()
    hints = STATE_INFERENCE.get(category, {}).get(entity_type, {})
    for patterns, state in hints.items():
        for pattern in patterns.split("|"):
            if pattern.strip() in content_lower:
                return state
    return "unknown"


def _generate_summary(content: str, entity_value: str, state: str) -> str:
    """
    Generate a concise state summary (max 200 chars).
    No LLM — just truncate and annotate.
    """
    truncated = content[:150].replace('\n', ' ').strip()
    if len(content) > 150:
        truncated += "..."
    return f"[{state.upper()}] {truncated}"


def upsert_state(
    entry_id: int,
    project_id: int,
    category: str,
    content: str,
    entities: list,
    db_path: str = "data/iuxis.db",
):
    """
    Update entity_states based on a newly written knowledge entry.
    Called from knowledge_manager after entity extraction.

    Only updates entities with confidence >= 0.8 to avoid noise.
    """
    if not entities:
        return

    conn = sqlite3.connect(db_path, check_same_thread=False)
    now = datetime.now(timezone.utc).isoformat()

    try:
        for entity in entities:
            # Only process high-confidence subject entities
            if entity.confidence < 0.8 or entity.role == "object":
                continue
            # Skip constraint entities from state tracking (too noisy)
            if entity.entity_type == "constraint":
                continue

            inferred_state = _infer_state(category, entity.entity_type, content)
            summary = _generate_summary(content, entity.entity_value, inferred_state)

            # Load existing state history
            existing = conn.execute(
                """SELECT id, state_history, current_state
                   FROM entity_states
                   WHERE entity_type = ? AND entity_value = ? AND project_id = ?""",
                [entity.entity_type, entity.entity_value, project_id]
            ).fetchone()

            history_entry = {
                "entry_id": entry_id,
                "state": inferred_state,
                "summary": summary[:200],
                "timestamp": now,
            }

            if existing:
                state_id, history_json, prev_state = existing
                history = json.loads(history_json) if history_json else []
                history.append(history_entry)
                # Keep last 20 history entries
                history = history[-20:]

                conn.execute(
                    """UPDATE entity_states
                       SET current_state = ?,
                           current_summary = ?,
                           last_entry_id = ?,
                           last_updated_at = ?,
                           confidence = ?,
                           state_history = ?
                       WHERE id = ?""",
                    [
                        inferred_state if inferred_state != "unknown" else prev_state,
                        summary,
                        entry_id,
                        now,
                        entity.confidence,
                        json.dumps(history),
                        state_id,
                    ]
                )
            else:
                history = [history_entry]
                conn.execute(
                    """INSERT INTO entity_states
                       (entity_type, entity_value, project_id, current_state,
                        current_summary, last_entry_id, last_updated_at,
                        confidence, state_history)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        entity.entity_type,
                        entity.entity_value,
                        project_id,
                        inferred_state,
                        summary,
                        entry_id,
                        now,
                        entity.confidence,
                        json.dumps(history),
                    ]
                )

        conn.commit()
    except Exception as exc:
        logger.warning(f"[EntityStateManager] upsert_state failed for entry {entry_id}: {exc}")
    finally:
        conn.close()


def get_project_states(
    project_id: int,
    entity_types: Optional[list] = None,
    db_path: str = "data/iuxis.db",
) -> list:
    """
    Retrieve all current entity states for a project.
    Used by the briefing engine as Tier 2 context.

    Returns list of state dicts, sorted by last_updated_at desc.
    Excludes 'unknown' states — they add noise without signal.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        query = """
            SELECT entity_type, entity_value, current_state,
                   current_summary, last_updated_at, confidence
            FROM entity_states
            WHERE project_id = ?
              AND current_state != 'unknown'
        """
        params = [project_id]

        if entity_types:
            placeholders = ",".join("?" * len(entity_types))
            query += f" AND entity_type IN ({placeholders})"
            params.extend(entity_types)

        query += " ORDER BY last_updated_at DESC"

        rows = conn.execute(query, params).fetchall()
        return [
            {
                "entity_type": r[0],
                "entity_value": r[1],
                "current_state": r[2],
                "current_summary": r[3],
                "last_updated_at": r[4],
                "confidence": r[5],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning(f"[EntityStateManager] get_project_states failed: {exc}")
        return []
    finally:
        conn.close()


def get_all_project_states_summary(
    project_ids: list,
    db_path: str = "data/iuxis.db",
) -> str:
    """
    Build a compact plaintext summary of current entity states
    across multiple projects. Used as Tier 2 context in briefing.

    Format:
        ## Current State: Health Data Vault
        - technology:aws nitro enclaves → ADOPTED
        - technology:fastapi → ADOPTED
        - decision_subject:payment processor → DECIDED
        ...
    """
    if not project_ids:
        return ""

    conn = sqlite3.connect(db_path, check_same_thread=False)
    lines = []

    try:
        for project_id in project_ids:
            project = conn.execute(
                "SELECT name FROM projects WHERE id = ?", [project_id]
            ).fetchone()
            if not project:
                continue

            states = get_project_states(project_id, db_path=db_path)
            if not states:
                continue

            lines.append(f"\n## Current State: {project[0]}")
            for s in states:
                age = ""
                if s["last_updated_at"]:
                    try:
                        updated = datetime.fromisoformat(
                            s["last_updated_at"].replace("Z", "+00:00")
                        )
                        days_ago = (datetime.now(timezone.utc) - updated).days
                        if days_ago > 7:
                            age = f" ({days_ago}d ago)"
                    except Exception:
                        pass
                lines.append(
                    f"- {s['entity_type']}:{s['entity_value']} "
                    f"→ {s['current_state'].upper()}{age}"
                )
                if s["current_summary"]:
                    lines.append(f"  {s['current_summary'][:120]}")

    except Exception as exc:
        logger.warning(f"[EntityStateManager] summary generation failed: {exc}")
    finally:
        conn.close()

    return "\n".join(lines)


def flag_stale_states(
    stale_threshold_days: int = 60,
    db_path: str = "data/iuxis.db",
) -> list:
    """
    Find entity states that haven't been updated in stale_threshold_days
    despite the project having recent activity.

    These are candidates for the insights engine to surface to the user.
    Returns list of dicts with entity info + days_stale.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    stale = []

    try:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=stale_threshold_days)
        ).isoformat()

        # Find entity states not updated since cutoff
        rows = conn.execute(
            """SELECT es.entity_type, es.entity_value, es.current_state,
                      es.last_updated_at, es.project_id, p.name as project_name
               FROM entity_states es
               JOIN projects p ON p.id = es.project_id
               WHERE es.last_updated_at < ?
                 AND es.current_state NOT IN ('complete', 'deprecated', 'rejected')
               ORDER BY es.last_updated_at ASC""",
            [cutoff]
        ).fetchall()

        for row in rows:
            project_id = row[4]
            # Check if project has had recent activity (tasks or knowledge updates)
            recent_activity = conn.execute(
                """SELECT COUNT(*) FROM user_knowledge
                   WHERE project_id = ?
                     AND created_at > ?""",
                [project_id, cutoff]
            ).fetchone()[0]

            if recent_activity > 0:
                try:
                    updated = datetime.fromisoformat(
                        row[3].replace("Z", "+00:00")
                    )
                    days_stale = (datetime.now(timezone.utc) - updated).days
                except Exception:
                    days_stale = stale_threshold_days

                stale.append({
                    "entity_type": row[0],
                    "entity_value": row[1],
                    "current_state": row[2],
                    "last_updated_at": row[3],
                    "project_name": row[5],
                    "days_stale": days_stale,
                    "recent_activity_count": recent_activity,
                })

    except Exception as exc:
        logger.warning(f"[EntityStateManager] flag_stale_states failed: {exc}")
    finally:
        conn.close()

    return stale


def get_pending_contradictions(
    db_path: str = "data/iuxis.db",
) -> list:
    """
    Return pending contradiction flags for UI display.
    These are surfaced in the dashboard for user resolution.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        rows = conn.execute(
            """SELECT cf.id, cf.entry_id_a, cf.entry_id_b,
                      cf.similarity_score, cf.conflict_type, cf.created_at,
                      a.content as content_a, b.content as content_b,
                      a.category as category_a, b.category as category_b
               FROM contradiction_flags cf
               JOIN user_knowledge a ON a.id = cf.entry_id_a
               JOIN user_knowledge b ON b.id = cf.entry_id_b
               WHERE cf.status = 'pending'
               ORDER BY cf.similarity_score DESC
               LIMIT 10"""
        ).fetchall()
        return [
            {
                "id": r[0],
                "entry_id_a": r[1], "entry_id_b": r[2],
                "similarity_score": r[3],
                "conflict_type": r[4],
                "created_at": r[5],
                "content_a": r[6][:200], "content_b": r[7][:200],
                "category_a": r[8], "category_b": r[9],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning(f"[EntityStateManager] get_pending_contradictions failed: {exc}")
        return []
    finally:
        conn.close()
