"""
Priority Engine — AI-powered task ranking.
Uses Qwen3.5 via LM Studio to rank tasks based on deadlines, dependencies,
project priority, and strategic importance.
"""
from datetime import date, datetime
import json
import logging

from iuxis.llm_client import LLMClient
from iuxis.db import get_connection, fetch_all

logger = logging.getLogger(__name__)


class PriorityEngine:
    def __init__(self):
        self.conn = get_connection()
        self.llm = LLMClient()

    def rank_tasks_for_today(self) -> list[dict]:
        """
        AI-rank all active tasks and return ordered list.
        Considers: task priority, project priority, due dates,
        estimated hours, current focus areas.
        """
        tasks = fetch_all(
            """SELECT t.id, t.title, t.priority, t.status, t.due_date,
                   t.estimated_hours, p.name as project_name,
                   p.priority as project_priority,
                   p.time_allocation_hrs_week, p.current_focus
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE t.status IN ('todo', 'in_progress')
            ORDER BY t.priority ASC"""
        )

        if not tasks:
            return []

        # For small task lists (<10), use rule-based ranking (no LLM needed)
        if len(tasks) <= 10:
            return self._rule_based_rank(tasks)

        # For larger lists, use Ollama for intelligent ranking
        return self._ai_rank(tasks)

    def _rule_based_rank(self, tasks: list[dict]) -> list[dict]:
        """Fast rule-based ranking for small task sets."""
        scored = []
        today = date.today()

        for t in tasks:
            tid = t.get("id")
            title = t.get("title", "Unknown")
            pri = t.get("priority", 5)
            status = t.get("status", "todo")
            due = t.get("due_date")
            hours = t.get("estimated_hours")
            proj = t.get("project_name") or "General"
            proj_pri = t.get("project_priority", 5)

            score = 0

            # Task priority (P1=40, P2=30, P3=20, P4=10, P5=5)
            score += max(50 - (pri * 10), 5)

            # Project priority boost
            score += max(30 - (proj_pri * 5), 5)

            # Due date urgency
            if due:
                try:
                    due_date = datetime.strptime(due, '%Y-%m-%d').date()
                    days_until = (due_date - today).days
                    if days_until < 0:
                        score += 50  # Overdue
                    elif days_until == 0:
                        score += 40  # Due today
                    elif days_until <= 3:
                        score += 30  # Due soon
                    elif days_until <= 7:
                        score += 15  # Due this week
                except ValueError:
                    pass

            # In-progress bonus
            if status == 'in_progress':
                score += 15

            scored.append({
                'id': tid,
                'title': title,
                'project': proj,
                'priority': pri,
                'due_date': due,
                'estimated_hours': hours,
                'score': score,
                'status': status
            })

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored

    def _ai_rank(self, tasks: list[dict]) -> list[dict]:
        """Use Qwen3.5 to rank tasks with strategic reasoning."""
        task_text = "\n".join([
            f"- ID:{t.get('id')} | {t.get('title', 'Unknown')} | P{t.get('priority', 5)} | {t.get('status', 'todo')} | Project: {t.get('project_name') or 'General'} (P{t.get('project_priority', 5)}) | Due: {t.get('due_date') or 'none'} | Est: {t.get('estimated_hours') or '?'}h"
            for t in tasks
        ])

        prompt = f"""Rank these tasks for today in order of what should be worked on first.

Today is {date.today().strftime('%A, %B %d, %Y')}.

<tasks>
{task_text}
</tasks>

SCORING CRITERIA:
- Strategic importance of parent project (P1 projects score higher)
- Deadline proximity (overdue > due today > due this week)
- Whether it blocks other tasks (blocking tasks score higher)
- Task status (in-progress tasks score higher than todo)
- If no deadline, score based on project priority only

Return ONLY a JSON array of task IDs in priority order, most important first:
[task_id_1, task_id_2, task_id_3, ...]

Example: [42, 17, 28, 9, 15]"""

        try:
            response = self.llm.generate_fast(prompt, format_json=True)
        except Exception as e:
            logger.warning(f"[PriorityEngine] LLM ranking failed: {e}, using rule-based fallback")
            return self._rule_based_rank(tasks)

        if not response:
            return self._rule_based_rank(tasks)

        # Parse JSON with robust handling
        ranked_ids = self._parse_ranking_response(response)
        if not ranked_ids:
            logger.warning("[PriorityEngine] Could not parse ranking, using rule-based fallback")
            return self._rule_based_rank(tasks)

        # Map back to task dicts
        task_map = {t.get("id"): t for t in tasks}
        result = []
        for tid in ranked_ids:
            if tid in task_map:
                t = task_map[tid]
                result.append({
                    'id': t.get('id'),
                    'title': t.get('title', 'Unknown'),
                    'project': t.get('project_name') or 'General',
                    'priority': t.get('priority', 5),
                    'due_date': t.get('due_date'),
                    'estimated_hours': t.get('estimated_hours'),
                    'status': t.get('status', 'todo')
                })
        return result

    def _parse_ranking_response(self, raw: str) -> list:
        """Extract task ID array from LLM response."""
        # Strip markdown fences
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(raw)

            # Handle different response formats
            if isinstance(parsed, list):
                # Format 1: Simple array [19, 20, 28, ...]
                return parsed
            elif isinstance(parsed, dict):
                # Try various dict formats
                if 'tasks' in parsed:
                    # Format 2: {"tasks": [{"id": 19}, ...]}
                    return [task.get('id') for task in parsed['tasks'] if 'id' in task]
                elif 'ranked_ids' in parsed:
                    # Format 3: {"ranked_ids": [19, 20, ...]}
                    return parsed['ranked_ids']
                elif 'response' in parsed and isinstance(parsed['response'], list):
                    # Format 4: {"response": [19, 20, ...]}
                    return parsed['response']
        except json.JSONDecodeError as e:
            logger.warning(f"[PriorityEngine] JSON parse failed: {e}, raw: {raw[:200]}")

        return []



# ---------------------------------------------------------------------------
# LLM singleton (replaces claude_client legacy calls)
# ---------------------------------------------------------------------------
_llm_singleton = None

def _get_llm_client():
    global _llm_singleton
    if _llm_singleton is None:
        from iuxis.llm_client import LLMClient
        _llm_singleton = LLMClient()
    return _llm_singleton

# Legacy functions for backward compatibility
def run_prioritization() -> str:
    """Ask Claude to prioritize current tasks. Returns the analysis text."""
    _llm = _get_llm_client()
    response = _llm.generate(
        prompt="Review the current task list and rank tasks by priority for today. Consider project urgency, deadlines, and dependencies. Return a brief prioritized list with reasoning.",
        system_prompt="You are an AI Chief of Staff helping a solo operator decide what to work on first."
    )
    return response


def generate_daily_schedule() -> str:
    """Ask Claude to generate a time-blocked schedule for today."""
    _llm = _get_llm_client()
    response = _llm.generate(
        prompt=(
            "Generate a concrete time-blocked schedule for today. "
            "Use the project priorities and task list from the context. "
            "Format each block as: TIME — PROJECT — TASK/ACTIVITY. "
            "Include breaks. Start and end times should match work hours from config."
        ),
        system_prompt="You are an AI Chief of Staff generating a daily schedule for a solo operator managing multiple concurrent projects."
    )
    return response
