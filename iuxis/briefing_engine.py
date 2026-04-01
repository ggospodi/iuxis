"""
Morning Briefing Engine for Iuxis.
Generates a daily priority briefing using Qwen3.5-35B-A3B via LM Studio.
"""
import re
import logging
import os
from datetime import date, datetime
from iuxis.llm_client import LLMClient
from iuxis.db import get_connection, fetch_all, execute
from iuxis.entity_state_manager import get_all_project_states_summary, flag_stale_states

logger = logging.getLogger(__name__)


def _strip_thinking(text: str) -> str:
    """Strip model thinking/reasoning blocks from LLM output."""
    if not text:
        return text
    # Strip <think>...</think> blocks (DeepSeek/Qwen style)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # If a ## heading exists, strip everything before it
    match = re.search(r'^#{1,3}\s', text, flags=re.MULTILINE)
    if match:
        return text[match.start():].strip()
    # No heading — find first real content line (bullet, bold, Deadline)
    content_match = re.search(
        r'^(\s*[-•]\s|\*\*|Deadline\s|⚠)',
        text,
        flags=re.MULTILINE
    )
    if content_match:
        return text[content_match.start():].strip()
    return text.strip()


def _is_clean(text: str) -> bool:
    """Return False if the text looks like it contains thinking noise."""
    if not text:
        return False
    lowered = text.strip().lower()
    return not (
        lowered.startswith('thinking process') or
        lowered.startswith('<think>') or
        lowered.startswith('1.') and 'analyze the request' in lowered[:100]
    )


class BriefingEngine:
    def __init__(self):
        self.conn = get_connection()
        self.llm = LLMClient()

    def generate_morning_briefing(self) -> dict:
        """Generate Today's Focus briefing."""
        context = self._build_briefing_context()

        # /no_thinking disables Qwen's visible chain-of-thought
        prompt = f"""/no_thinking

Generate a concise morning briefing for {date.today().strftime('%A, %B %d, %Y')}.

<projects>
{context}
</projects>

INSTRUCTIONS:
- List the top 3–5 actionable priorities as bullets
- Each bullet: [Project Name]: [specific action in 10 words max]
- Include deadline alerts (tasks due in next 7 days)
- Note any blocked/stalled items
- End with ONE sentence: the single most important thing to accomplish today
- Total briefing: under 200 words
- No fluff, no preamble, no thinking process

Return plain markdown. Start directly with the first bullet point."""

        try:
            response = self.llm.generate_fast(prompt)
        except Exception as e:
            logger.error(f"[BriefingEngine] LLM generation failed: {e}")
            return {
                'briefing_text': f"⚠️ Failed to generate briefing: {e}",
                'generated_at': datetime.now().isoformat()
            }

        if not response:
            return {
                'briefing_text': "⚠️ Failed to generate briefing. Check that LM Studio is running.",
                'generated_at': datetime.now().isoformat()
            }

        # Strip any remaining thinking blocks before storing
        response = _strip_thinking(response)

        execute(
            """INSERT INTO insights (type, content, severity, status, created_at)
               VALUES ('recommendation', ?, 'info', 'new', ?)""",
            (response, datetime.now().isoformat())
        )

        return {
            'briefing_text': response,
            'generated_at': datetime.now().isoformat()
        }

    def _build_briefing_context(self) -> str:
        """Build comprehensive context for briefing generation."""
        sections = []

        projects = fetch_all(
            """SELECT p.name, p.priority, p.status, p.current_focus,
                   p.time_allocation_hrs_week, p.type
            FROM projects p
            WHERE p.parent_id IS NULL AND p.status = 'active'
            ORDER BY p.priority ASC"""
        )

        if projects:
            proj_lines = ["[ACTIVE PROJECTS]"]
            for row in projects:
                name = row.get("name", "Unknown")
                pri = row.get("priority", 5)
                ptype = row.get("type", "unknown")
                hours = row.get("time_allocation_hrs_week", 0)
                focus = row.get("current_focus") or "not set"
                proj_lines.append(f"- P{pri}: {name} ({ptype}, {hours}h/wk) — Focus: {focus}")
            sections.append("\n".join(proj_lines))

        tasks = fetch_all(
            """SELECT t.title, t.priority, t.status, t.due_date,
                   t.estimated_hours, p.name as project_name
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE t.status IN ('todo', 'in_progress')
            ORDER BY t.priority ASC, t.due_date ASC"""
        )

        if tasks:
            task_lines = ["[ACTIVE TASKS]"]
            for row in tasks:
                title = row.get("title", "Unknown")
                pri = row.get("priority", 5)
                status = row.get("status", "todo")
                due = row.get("due_date")
                hours = row.get("estimated_hours")
                proj = row.get("project_name") or "General"
                due_str = f" (due: {due})" if due else ""
                hrs_str = f" [{hours}h]" if hours else ""
                task_lines.append(f"- P{pri} [{status}] {title} — {proj}{due_str}{hrs_str}")
            sections.append("\n".join(task_lines))

        knowledge = fetch_all(
            """SELECT uk.content, uk.category, p.name
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            WHERE uk.status = 'approved'
            ORDER BY uk.created_at DESC
            LIMIT 15"""
        )

        if knowledge:
            know_lines = ["[RECENT KNOWLEDGE]"]
            for row in knowledge:
                content = row.get("content", "")
                cat = row.get("category", "unknown")
                proj = row.get("name") or "General"
                know_lines.append(f"- [{proj}/{cat}] {content}")
            sections.append("\n".join(know_lines))

        project_ids = [p.get("id") for p in fetch_all(
            "SELECT id FROM projects WHERE status = 'active' ORDER BY priority ASC"
        )]
        if project_ids:
            conn = get_connection()
            db_path = None
            try:
                cursor = conn.execute("PRAGMA database_list")
                for row in cursor:
                    if row[1] == 'main':
                        db_path = row[2]
                        break
            except:
                db_path = os.path.expanduser("~/Desktop/iuxis/data/iuxis.db")

            if db_path:
                entity_states = get_all_project_states_summary(project_ids, db_path=db_path)
                if entity_states:
                    sections.append(f"[CURRENT ENTITY STATES]\n{entity_states}")

                stale = flag_stale_states(stale_threshold_days=45, db_path=db_path)
                if stale:
                    stale_lines = ["[STALE CONTEXT WARNINGS]"]
                    stale_lines.append("These tracked items haven't been updated recently despite project activity:")
                    for s in stale[:5]:
                        stale_lines.append(
                            f"  ⚠️ {s['project_name']}: {s['entity_type']}:{s['entity_value']} "
                            f"(state: {s['current_state']}, {s['days_stale']}d stale)"
                        )
                    sections.append("\n".join(stale_lines))

        activity = fetch_all(
            """SELECT event_type, details, created_at
            FROM activity_log
            WHERE created_at > datetime('now', '-2 days')
            ORDER BY created_at DESC
            LIMIT 10"""
        )

        if activity:
            act_lines = ["[RECENT ACTIVITY (48h)]"]
            for row in activity:
                etype = row.get("event_type", "unknown")
                details = row.get("details", "")
                details_short = details[:100] if details else "no details"
                act_lines.append(f"- {etype}: {details_short}")
            sections.append("\n".join(act_lines))

        return "\n\n".join(sections)

    def get_latest_briefing(self) -> str | None:
        """Get the most recent clean briefing from today."""
        rows = fetch_all(
            """SELECT content, created_at FROM insights
            WHERE type = 'recommendation'
            AND date(created_at) = date('now')
            ORDER BY created_at DESC LIMIT 10"""
        )
        for row in rows:
            content = row.get("content", "")
            cleaned = _strip_thinking(content)
            if _is_clean(cleaned):
                return cleaned
        return None
