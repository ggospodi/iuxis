"""
PREMIUM FEATURE: Automated Memory Consolidation
Nightly APScheduler job at 2:00 AM.
Consolidates chat-sourced knowledge entries into structured summaries.

Requires: active premium license (stubbed to True in development)
LLM: Uses Ollama/DeepSeek fallback — runs even when LM Studio is closed.
"""

import logging
import json
import sqlite3
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from iuxis.premium.license import require_premium

logger = logging.getLogger("iuxis.consolidation")

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "deepseek-r1:32b"
DB_PATH = "data/iuxis.db"


def _get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _call_ollama(prompt: str, max_tokens: int = 800) -> str:
    """Direct Ollama call for consolidation — bypasses LLMClient to avoid LM Studio dep."""
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.3}
        }
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        content = r.json()["message"]["content"]
        # Strip DeepSeek think blocks
        if "<think>" in content:
            content = content.split("</think>")[-1].strip()
        return content.strip()
    except Exception as e:
        logger.error(f"[Consolidation] Ollama call failed: {e}")
        return ""


def fetch_recent_chat_knowledge(days: int = 7, project_id: Optional[int] = None) -> List[Dict]:
    """Fetch unconsolidated chat-sourced knowledge entries from the last N days."""
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    if project_id:
        rows = conn.execute(
            """SELECT id, category, content, source, confidence, importance, project_id, created_at
               FROM user_knowledge
               WHERE source = 'chat'
               AND consolidated = 0
               AND created_at >= ?
               AND project_id = ?
               ORDER BY created_at ASC""",
            (cutoff, project_id)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, category, content, source, confidence, importance, project_id, created_at
               FROM user_knowledge
               WHERE source = 'chat'
               AND consolidated = 0
               AND created_at >= ?
               ORDER BY created_at ASC""",
            (cutoff,)
        ).fetchall()

    conn.close()
    return [
        {
            "id": r[0], "category": r[1], "content": r[2],
            "source": r[3], "confidence": r[4], "importance": r[5],
            "project_id": r[6], "created_at": r[7]
        }
        for r in rows
    ]


def get_project_name(project_id: int) -> str:
    """Look up project name from DB."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else f"Project {project_id}"
    except Exception:
        return f"Project {project_id}"


def consolidate_group(entries: List[Dict], project_name: str) -> str:
    """
    Ask LLM to consolidate a group of entries into a structured summary.
    Uses /no_think for speed — this is a summarization task, not complex reasoning.
    """
    entries_text = "\n".join(
        f"- [{e['category'].upper()}] {e['content']}" for e in entries
    )

    prompt = f"""/no_think
You are consolidating knowledge entries for: {project_name}

Compress these entries into ONE structured summary. Preserve:
- All decisions made (exact specifics, no generalization)
- All preferences stated
- All corrections and pivots
- Key facts, numbers, names, dates
- Any risks or blockers identified

Entries to consolidate:
{entries_text}

Write a concise bullet-point summary (max 350 words).
Start directly with bullets. No preamble.
"""
    return _call_ollama(prompt, max_tokens=600)


def save_consolidated_entry(
    summary: str,
    project_id: Optional[int],
    source_ids: List[int]
) -> int:
    """Write the consolidated summary back as a pinned knowledge entry."""
    from iuxis.importance import compute_importance

    project_name = get_project_name(project_id) if project_id else "Global"
    content = f"[Consolidated — {project_name}] {summary}"

    importance = compute_importance(
        category="decision",
        content=content,
        source="consolidation",
        confidence="high",
        pinned=True,
    )

    conn = _get_conn()
    cursor = conn.execute(
        """INSERT INTO user_knowledge
           (category, content, source, confidence, importance, pinned, project_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "decision", content, "consolidation", "high",
            importance, 1, project_id, datetime.now().isoformat()
        )
    )
    new_id = cursor.lastrowid

    # Mark source entries as consolidated
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        conn.execute(
            f"UPDATE user_knowledge SET consolidated = 1, consolidated_into = ? WHERE id IN ({placeholders})",
            [new_id] + source_ids
        )

    conn.commit()
    conn.close()
    return new_id


def record_consolidation_run(
    project_id: Optional[int],
    entries_processed: int,
    summary_entry_id: int,
    trigger: str = "scheduled"
):
    """Log the consolidation run to consolidation_runs table."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO consolidation_runs
           (run_at, project_id, entries_processed, summary_entry_id, trigger)
           VALUES (?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), project_id, entries_processed, summary_entry_id, trigger)
    )
    conn.commit()
    conn.close()


@require_premium("Memory Consolidation")
def run_consolidation_pass(trigger: str = "scheduled") -> Dict:
    """
    Main consolidation entry point.
    Groups chat entries by project, consolidates each group with >= 3 entries.

    Returns summary of what was done.
    """
    logger.info(f"[Consolidation] Starting pass (trigger={trigger})...")

    recent_entries = fetch_recent_chat_knowledge(days=7)

    if len(recent_entries) < 3:
        msg = f"Only {len(recent_entries)} unconsolidated chat entries — skipping (need >= 3)"
        logger.info(f"[Consolidation] {msg}")
        return {"status": "skipped", "reason": msg, "entries_found": len(recent_entries)}

    # Group by project_id (None = global/unassigned)
    by_project: Dict[Optional[int], List[Dict]] = {}
    for entry in recent_entries:
        pid = entry.get("project_id")
        by_project.setdefault(pid, []).append(entry)

    results = []
    total_consolidated = 0

    for pid, entries in by_project.items():
        if len(entries) < 3:
            logger.info(f"[Consolidation] Project {pid}: only {len(entries)} entries, skipping")
            continue

        project_name = get_project_name(pid) if pid else "Global"
        logger.info(f"[Consolidation] Consolidating {len(entries)} entries for {project_name}...")

        summary = consolidate_group(entries, project_name)
        if not summary:
            logger.warning(f"[Consolidation] Empty summary for {project_name}, skipping")
            continue

        source_ids = [e["id"] for e in entries]
        new_entry_id = save_consolidated_entry(summary, pid, source_ids)
        record_consolidation_run(pid, len(entries), new_entry_id, trigger)

        total_consolidated += len(entries)
        results.append({
            "project_id": pid,
            "project_name": project_name,
            "entries_consolidated": len(entries),
            "summary_entry_id": new_entry_id,
        })
        logger.info(f"[Consolidation] {project_name}: {len(entries)} → entry #{new_entry_id}")

    status = "complete" if results else "skipped"
    logger.info(f"[Consolidation] Pass complete. {total_consolidated} entries consolidated across {len(results)} projects.")

    return {
        "status": status,
        "trigger": trigger,
        "run_at": datetime.now().isoformat(),
        "total_entries_consolidated": total_consolidated,
        "projects": results,
    }


def get_consolidation_history(limit: int = 10) -> List[Dict]:
    """Fetch recent consolidation run history."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT cr.id, cr.run_at, cr.project_id, cr.entries_processed,
                  cr.summary_entry_id, cr.trigger,
                  p.name as project_name
           FROM consolidation_runs cr
           LEFT JOIN projects p ON cr.project_id = p.id
           ORDER BY cr.run_at DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0], "run_at": r[1], "project_id": r[2],
            "entries_processed": r[3], "summary_entry_id": r[4],
            "trigger": r[5], "project_name": r[6]
        }
        for r in rows
    ]
