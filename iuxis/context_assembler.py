"""Context assembly for Claude API calls with ~8000 token budget."""
from __future__ import annotations

import os
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from iuxis.db import fetch_all, get_connection
from iuxis.project_manager import list_projects
from iuxis.task_manager import get_todays_tasks
from iuxis.models import Project, Task, ScheduleBlock, Insight
from iuxis import knowledge_manager
from iuxis.query_classifier import classify_query, QueryType, ClassifiedQuery
from iuxis.entity_state_manager import get_all_project_states_summary, flag_stale_states

logger = logging.getLogger(__name__)


# Token estimation: rough approximation (1 token ≈ 4 chars)
def estimate_tokens(text: str) -> int:
    """Estimate token count for text (rough heuristic: ~4 chars per token)."""
    return len(text) // 4


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


# ---------------------------------------------------------------------------
# Section Builders
# ---------------------------------------------------------------------------

def build_project_summary(max_tokens: int = 1500) -> str:
    """Build [PROJECT_SUMMARY] section (~1500 tokens).

    All projects with name/type/status/priority/focus/time_allocation
    and parent-child relationships.
    """
    projects = list_projects()
    if not projects:
        return "[PROJECT_SUMMARY]\nNo projects registered yet."

    # Build hierarchical view
    by_id = {p.id: {"project": p, "children": []} for p in projects}
    roots = []

    for p in projects:
        node = by_id[p.id]
        if p.parent_id and p.parent_id in by_id:
            by_id[p.parent_id]["children"].append(node)
        else:
            roots.append(node)

    lines = ["[PROJECT_SUMMARY]"]

    def render_project(node: dict, indent: int = 0) -> list[str]:
        p: Project = node["project"]
        prefix = "  " * indent
        status_icon = {
            "active": "🟢", "paused": "⏸️", "blocked": "🔴", "monitoring": "👁️"
        }.get(p.status.value, "⚪")

        line = (
            f"{prefix}#{p.id} [{status_icon} P{p.priority}] {p.name} ({p.type.value}) "
            f"— {p.time_allocation_hrs_week}h/wk"
        )
        if p.current_focus:
            line += f"\n{prefix}  Focus: {p.current_focus[:100]}"

        result = [line]
        for child in node["children"]:
            result.extend(render_project(child, indent + 1))
        return result

    for root in roots:
        lines.extend(render_project(root))

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


def build_todays_tasks(max_tokens: int = 1000) -> str:
    """Build [TODAYS_TASKS] section (~1000 tokens).

    Tasks due today + in_progress tasks.
    """
    tasks = get_todays_tasks()
    if not tasks:
        return "[TODAYS_TASKS]\nNo tasks due today or in progress."

    lines = ["[TODAYS_TASKS]"]
    for t in tasks:
        proj = f" [{t.project_name}]" if t.project_name else ""
        due_str = f" due:{t.due_date}" if t.due_date else ""
        est_str = f" ~{t.estimated_hours}h" if t.estimated_hours else ""
        status_icon = {
            "todo": "⬜", "in_progress": "🔵", "blocked": "🔴", "done": "✅"
        }.get(t.status.value, "⬜")

        line = f"  #{t.id}{proj} [P{t.priority} {status_icon}] {t.title}{due_str}{est_str}"
        if t.description:
            line += f"\n    → {t.description[:150]}"
        lines.append(line)

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


def build_todays_schedule(max_tokens: int = 500) -> str:
    """Build [TODAYS_SCHEDULE] section (~500 tokens).

    Today's schedule blocks.
    """
    today = date.today().isoformat()
    rows = fetch_all(
        """SELECT sb.*, p.name as project_name, t.title as task_title
           FROM schedule_blocks sb
           LEFT JOIN projects p ON sb.project_id = p.id
           LEFT JOIN tasks t ON sb.task_id = t.id
           WHERE sb.date = ?
           ORDER BY sb.start_time ASC""",
        (today,)
    )

    if not rows:
        return "[TODAYS_SCHEDULE]\nNo schedule blocks for today."

    blocks = [ScheduleBlock.from_row(r) for r in rows]
    lines = ["[TODAYS_SCHEDULE]"]

    for b in blocks:
        status_icon = {"planned": "⏳", "active": "▶️", "completed": "✅", "skipped": "⏭️"}.get(b.status, "⏳")
        proj = f"[{b.project_name}] " if b.project_name else ""
        task = f"{b.task_title}" if b.task_title else b.block_type.value
        line = f"  {b.start_time} - {b.end_time} {status_icon} {proj}{task}"
        lines.append(line)

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


def build_recent_activity(max_tokens: int = 500) -> str:
    """Build [RECENT_ACTIVITY] section (~500 tokens).

    Last 48hrs of activity_log.
    """
    rows = fetch_all(
        """SELECT * FROM activity_log
           WHERE created_at > datetime('now', '-2 days')
           ORDER BY created_at DESC LIMIT 30"""
    )

    if not rows:
        return "[RECENT_ACTIVITY]\nNo recent activity."

    lines = ["[RECENT_ACTIVITY]"]
    for a in rows:
        timestamp = a.get("created_at", "")
        if timestamp:
            # Parse and format timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m/%d %H:%M")
            except:
                time_str = timestamp[:16]
        else:
            time_str = "???"

        event = a.get("event_type", "unknown")
        details = a.get("details", "")
        line = f"  [{time_str}] {event}"
        if details:
            line += f": {details[:80]}"
        lines.append(line)

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


def build_recent_insights(max_tokens: int = 500) -> str:
    """Build [RECENT_INSIGHTS] section (~500 tokens).

    Unresolved insights.
    """
    rows = fetch_all(
        "SELECT * FROM insights WHERE status = 'new' ORDER BY created_at DESC LIMIT 10"
    )

    if not rows:
        return "[RECENT_INSIGHTS]\nNo unresolved insights."

    insights = [Insight.from_row(r) for r in rows]
    lines = ["[RECENT_INSIGHTS]"]

    for i in insights:
        severity_icon = {
            "info": "ℹ️", "warning": "⚠️", "action_required": "🚨"
        }.get(i.severity.value, "ℹ️")

        line = f"  {severity_icon} [{i.type.value}] {i.content[:200]}"
        lines.append(line)

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


def build_entity_states(project_id: Optional[int] = None, max_tokens: int = 1000) -> str:
    """Build current entity states section for Tier 2 context."""
    if project_id:
        project_ids = [project_id]
    else:
        # Get all active project IDs
        conn = get_connection()
        rows = fetch_all(
            "SELECT id FROM projects WHERE status = 'active' ORDER BY priority ASC"
        )
        project_ids = [r.get("id") for r in rows]

    if not project_ids:
        return ""

    # Get database path from connection
    # SQLite connections have a way to get the database path
    conn = get_connection()
    db_path = None
    try:
        # Try to get database path from cursor
        cursor = conn.execute("PRAGMA database_list")
        for row in cursor:
            if row[1] == 'main':  # main database
                db_path = row[2]
                break
    except:
        # Fallback: assume standard path
        db_path = os.path.expanduser("~/Desktop/iuxis/data/iuxis.db")

    if not db_path:
        return ""

    summary = get_all_project_states_summary(project_ids, db_path=db_path)

    if not summary:
        return ""

    # Add header and truncate if needed
    text = f"[CURRENT_ENTITY_STATES]\n{summary}"
    return truncate_to_tokens(text, max_tokens)


def project_name_to_slug(name: str) -> str:
    """Convert project name to filesystem-friendly slug."""
    return name.lower().replace(" ", "-").replace("_", "-")


def detect_project_from_message(user_message: str) -> Optional[int]:
    """Return project_id if user message references a known project."""
    conn = get_connection()
    projects = fetch_all(
        "SELECT id, name FROM projects WHERE parent_id IS NULL"
    )

    msg_lower = user_message.lower()
    for row in projects:
        pid = row.get("id")
        name = row.get("name", "")
        if name and name.lower() in msg_lower:
            return pid
    return None


def build_project_knowledge(project_id: int, query: str = "", max_tokens: int = 1000, limit: int = 15) -> str:
    """Get knowledge entries for a specific project using hybrid semantic+SQL retrieval."""
    # Use hybrid retrieval if query provided, otherwise fall back to SQL
    if query.strip():
        entries = knowledge_manager.search_hybrid(query=query, project_id=project_id, topk=limit)
    else:
        # Fallback to SQL-only retrieval
        entries = knowledge_manager.get_project_knowledge(project_id=project_id, limit=limit)

    if not entries:
        return "[PROJECT_KNOWLEDGE]\nNo knowledge entries for this project yet."

    lines = ["[PROJECT_KNOWLEDGE]"]
    for entry in entries:
        content = entry.get("content", "")
        category = entry.get("category", "unknown")
        created_at = entry.get("created_at", "")
        importance = entry.get("importance", 0.5)
        semantic_score = entry.get("semantic_score", 0.0)
        date_str = created_at[:10] if created_at else "unknown"

        # Add relevance indicator for high-scoring entries
        relevance = ""
        if semantic_score > 0.7 or importance > 0.8:
            relevance = " ⭐"

        lines.append(f"- [{category}]{relevance} ({date_str}) {content}")

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


def build_cross_project_knowledge(query: str = "", max_tokens: int = 1000, limit: int = 20) -> str:
    """Get recent knowledge entries across all projects using hybrid retrieval."""
    # Use hybrid retrieval if query provided, otherwise fall back to SQL
    if query.strip():
        entries = knowledge_manager.search_hybrid(query=query, project_id=None, topk=limit)
    else:
        # Fallback to SQL-only retrieval
        rows = fetch_all(
            """SELECT uk.id, uk.content, uk.category, p.name as project_name, uk.created_at, uk.importance
               FROM user_knowledge uk
               LEFT JOIN projects p ON uk.project_id = p.id
               WHERE uk.status = 'approved'
               ORDER BY uk.created_at DESC
               LIMIT ?""",
            (limit,)
        )
        entries = [dict(r) for r in rows]

    if not entries:
        return "[PROJECT_KNOWLEDGE]\nNo knowledge entries yet."

    lines = ["[PROJECT_KNOWLEDGE]"]
    for entry in entries:
        content = entry.get("content", "")
        category = entry.get("category", "unknown")
        project_name = entry.get("project_name") or "General"
        created_at = entry.get("created_at", "")
        importance = entry.get("importance", 0.5)
        semantic_score = entry.get("semantic_score", 0.0)
        date_str = created_at[:10] if created_at else "unknown"

        # Add relevance indicator for high-scoring entries
        relevance = ""
        if semantic_score > 0.7 or importance > 0.8:
            relevance = " ⭐"

        lines.append(f"- [{project_name}/{category}]{relevance} ({date_str}) {content}")

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


def build_knowledge_by_query_type(
    classification: ClassifiedQuery,
    user_message: str,
    project_id: Optional[int] = None,
) -> tuple[str, str]:
    """
    Route to appropriate knowledge retrieval based on query type.

    Returns (strategy_name, formatted_section)
    """
    query_type = classification.query_type

    # Route based on query type
    if query_type == QueryType.FACTUAL_LOOKUP:
        # Simple SQL retrieval for facts - no semantic needed
        if project_id:
            entries = knowledge_manager.get_project_knowledge(
                project_id=project_id,
                category=None,  # Any category
                status="approved",
                limit=5
            )
        else:
            # Cross-project factual lookup
            entries = knowledge_manager.search_hybrid(query=user_message, project_id=None, topk=5)
        strategy = "sql_factual"

    elif query_type == QueryType.CURRENT_STATE:
        # Entity states are primary - supplement with recent entries only
        # Limit to fewer results (entity states cover most of it)
        entries = knowledge_manager.search_hybrid(query=user_message, project_id=project_id, topk=5)
        strategy = "entity_state_primary"

    elif query_type == QueryType.TEMPORAL_CHAIN:
        # Need more entries to show evolution - increase topk
        entries = knowledge_manager.search_hybrid(query=user_message, project_id=project_id, topk=15)
        # Sort by created_at to show chronological evolution
        entries = sorted(entries, key=lambda e: e.get('created_at', ''), reverse=False)
        strategy = "temporal_chain"

    elif query_type == QueryType.CROSS_PROJECT_SYNTHESIS:
        # Cross-project - no project_id filter, moderate topk
        entries = knowledge_manager.search_hybrid(query=user_message, project_id=None, topk=10)
        strategy = "cross_project"

    elif query_type == QueryType.RECENT_CONTEXT:
        # Recent only - increase topk but filter by recency in rendering
        entries = knowledge_manager.search_hybrid(query=user_message, project_id=project_id, topk=12)
        strategy = "recency_filtered"

    else:
        # Fallback: standard hybrid
        entries = knowledge_manager.search_hybrid(query=user_message, project_id=project_id, topk=8)
        strategy = "hybrid_fallback"

    # Format entries for context
    if not entries:
        return strategy, ""

    # Render section
    header = f"[RELEVANT_KNOWLEDGE] ({len(entries)} entries)\n"
    entry_lines = []
    for entry in entries:
        # Add relevance indicator
        importance = entry.get('importance', 0.5)
        sem_score = entry.get('semantic_score', 0.0)
        relevant = "⭐ " if (sem_score > 0.7 or importance > 0.8) else ""

        category = entry.get('category', 'unknown')
        created = entry.get('created_at', '')[:10]  # Just date
        content = entry.get('content', '')
        if len(content) > 300:  # Truncate long entries
            content = content[:300] + "..."

        entry_lines.append(
            f"{relevant}[{created}] ({category})\n{content}"
        )

    section = header + "\n---\n".join(entry_lines)
    section = truncate_to_tokens(section, 2000)  # Hard limit for knowledge section

    return strategy, section


def build_checkpoint_excerpt(project_slug: str, max_tokens: int = 500, max_chars: int = 2000) -> str:
    """Read the beginning of a project's checkpoint file."""
    checkpoint_path = os.path.expanduser(
        f"~/Desktop/iuxis/projects/{project_slug}/checkpoint.md"
    )
    if not os.path.exists(checkpoint_path):
        return ""

    with open(checkpoint_path, 'r') as f:
        content = f.read(max_chars)

    if len(content) >= max_chars:
        content = content[:max_chars].rsplit('\n', 1)[0] + "\n[...truncated]"

    text = f"[CHECKPOINT_EXCERPT]\n{content}"
    return truncate_to_tokens(text, max_tokens)


def build_channel_history(max_tokens: int = 1500, limit: int = 10) -> str:
    """Build [CHANNEL_HISTORY] section (~1500 tokens).

    Last 10 chat exchanges (20 messages: 10 user + 10 assistant).
    """
    rows = fetch_all(
        "SELECT role, content, created_at FROM chat_history ORDER BY created_at DESC LIMIT ?",
        (limit * 2,)
    )

    if not rows:
        return "[CHANNEL_HISTORY]\nNo chat history yet."

    # Reverse to chronological order
    rows = list(reversed(rows))

    lines = ["[CHANNEL_HISTORY]"]
    for msg in rows:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        role_icon = "👤" if role == "user" else "🤖"

        # Truncate individual messages if too long
        if len(content) > 500:
            content = content[:500] + "..."

        lines.append(f"\n{role_icon} {role.upper()}:")
        lines.append(content)

    text = "\n".join(lines)
    return truncate_to_tokens(text, max_tokens)


# ---------------------------------------------------------------------------
# Main Assembly Function
# ---------------------------------------------------------------------------

def assemble_context(user_message: str = "", channel_id: Optional[int] = None) -> dict:
    """
    Assemble tier-aware context for LLM with query classification.

    Sections:
    - [PROJECT_SUMMARY] (~1500 tokens)
    - [TODAYS_TASKS] (~1000 tokens)
    - [TODAYS_SCHEDULE] (~500 tokens)
    - [RECENT_ACTIVITY] (~500 tokens)
    - [RECENT_INSIGHTS] (~500 tokens)
    - [CURRENT_ENTITY_STATES] (~1000 tokens) - Tier 2 fast lookup
    - [RELEVANT_KNOWLEDGE] (~2000 tokens) - Query-type-aware retrieval
    - [CHECKPOINT_EXCERPT] (~500 tokens) - (if project detected)
    - [CHANNEL_HISTORY] (~1500 tokens)

    Args:
        user_message: User's message for query classification and project detection
        channel_id: Optional channel ID for filtering chat history (not yet implemented)

    Returns:
        Dict with context_text and metadata about retrieval strategy.
    """
    # 1. Classify the query
    classification = classify_query(user_message) if user_message else ClassifiedQuery(
        query_type=QueryType.CURRENT_STATE,
        confidence=0.5,
        strategy_notes="No query provided, defaulting to current_state"
    )
    logger.debug(f"[ContextAssembler] {classification.strategy_notes}")

    # 2. Detect project context
    project_id = detect_project_from_message(user_message) if user_message else None

    # 3. Build standard sections (always included)
    sections = []
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    metadata_lines = [
        f"=== CONTEXT SNAPSHOT ===",
        f"Date: {today} | Time: {now}",
        f"Query classification: {classification.query_type.value} (conf={classification.confidence:.2f})",
    ]
    sections.append("\n".join(metadata_lines))

    sections.append(build_project_summary(max_tokens=65536))
    sections.append(build_todays_tasks(max_tokens=65536))
    sections.append(build_todays_schedule(max_tokens=65536))
    sections.append(build_recent_activity(max_tokens=65536))
    sections.append(build_recent_insights(max_tokens=65536))

    # 4. Add entity states (Tier 2) - ALWAYS included for context awareness
    entity_state_section = build_entity_states(project_id, max_tokens=1000)
    if entity_state_section:
        sections.append(entity_state_section)

    # 5. Add knowledge section with query-type-aware retrieval
    retrieval_strategy = "none"
    if user_message:
        retrieval_strategy, knowledge_section = build_knowledge_by_query_type(
            classification, user_message, project_id
        )
        if knowledge_section:
            sections.append(knowledge_section)

    # 6. Add checkpoint excerpt if project detected
    if project_id:
        name_row = fetch_all(
            "SELECT name FROM projects WHERE id = ?", (project_id,)
        )
        if name_row and name_row[0].get("name"):
            slug = project_name_to_slug(name_row[0]["name"])
            checkpoint_section = build_checkpoint_excerpt(slug, max_tokens=65536)
            if checkpoint_section:
                sections.append(checkpoint_section)

    # 7. Add channel history
    sections.append(build_channel_history(max_tokens=65536))

    # 8. Assemble final context
    context_text = "\n\n".join(s for s in sections if s)

    return {
        "context_text": context_text,
        "query_type": classification.query_type.value,
        "confidence": classification.confidence,
        "strategy_used": retrieval_strategy,
        "entity_states_included": bool(entity_state_section),
        "metadata": {
            "project_hints": classification.project_hints,
            "time_scope": classification.time_scope,
            "entities_mentioned": classification.entities_mentioned,
        }
    }
