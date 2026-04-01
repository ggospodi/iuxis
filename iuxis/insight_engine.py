"""
Enhanced Insight Engine — generates cross-project observations.
Runs on demand or via scheduled job.
Uses Qwen3.5 with /think mode for deep analysis.
"""
from datetime import datetime
from typing import Optional
import json
import logging

from iuxis.db import execute, fetch_all, get_connection
from iuxis.llm_client import LLMClient
from iuxis.models import Insight, InsightSeverity

logger = logging.getLogger(__name__)


class InsightEngine:
    def __init__(self):
        self.conn = get_connection()
        self.llm = LLMClient()

    def generate_insights(self) -> list[dict]:
        """
        Analyze all projects and generate cross-project insights.
        Categories:
        - dependency: shared dependencies between projects
        - bottleneck: pattern suggesting a bottleneck or risk
        - opportunity: progress on one project unblocks another
        - conflict: resource conflict (same skill/time needed)
        """
        context = self._build_analysis_context()

        prompt = f"""Analyze the following project data and identify exactly 3 non-obvious insights.

<projects>
{context}
</projects>

An insight must be ONE of:
- A hidden dependency between two or more projects
- A pattern suggesting a bottleneck or risk
- An opportunity where progress on one project unblocks another
- A resource conflict (same skill/time needed in multiple projects)

Do NOT state obvious facts. Do NOT summarize project status.
Each insight: 2–3 sentences. Be specific — name projects, tasks, and dates.

Return ONLY this JSON, no other text:
{{
  "insights": [
    {{
      "title": "short title (max 8 words)",
      "body": "2-3 sentence insight",
      "projects_involved": ["Project A", "Project B"],
      "type": "dependency|bottleneck|opportunity|conflict",
      "severity": "info|warning|critical"
    }}
  ]
}}

Example:
{{
  "insights": [
    {{
      "title": "Tengrium and HDV share clinical dependency",
      "body": "Both Tengrium Health and HDV require clinical partnerships to proceed. Progress on either unblocks the other through shared partner network.",
      "projects_involved": ["Tengrium Health", "Health Data Vault"],
      "type": "dependency",
      "severity": "warning"
    }}
  ]
}}"""

        try:
            response = self.llm.generate_deep(prompt, format_json=True)
        except Exception as e:
            logger.error(f"[InsightEngine] LLM generation failed: {e}")
            return []

        if not response:
            return []

        # Parse JSON with robust handling
        parsed = self._parse_insights_response(response)
        if not parsed:
            return []

        saved = []
        for insight in parsed:
            try:
                execute(
                    """INSERT INTO insights (type, content, severity, status, created_at)
                    VALUES (?, ?, ?, 'new', ?)""",
                    (
                        insight.get('type', 'observation'),
                        f"{insight.get('title', 'Insight')}: {insight.get('body', '')}",
                        insight.get('severity', 'info'),
                        datetime.now().isoformat()
                    )
                )
                saved.append(insight)
            except Exception as e:
                logger.warning(f"[InsightEngine] Failed to save insight: {e}")
                continue

        return saved

    def _parse_insights_response(self, raw: str) -> list:
        """Extract insights JSON from LLM response, handling think blocks and markdown fences."""
        # Strip think blocks
        if "</think>" in raw:
            raw = raw.split("</think>")[-1].strip()

        # Strip markdown fences
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(raw)
            insights = data.get("insights", [])
            if isinstance(insights, list) and len(insights) > 0:
                return insights
        except json.JSONDecodeError as e:
            logger.warning(f"[InsightEngine] JSON parse failed: {e}, raw: {raw[:200]}")

        return []

    def _build_analysis_context(self) -> str:
        """Build context for cross-project analysis."""
        # Projects + allocations
        projects = fetch_all(
            """SELECT name, type, priority, status, current_focus,
                   time_allocation_hrs_week, updated_at
            FROM projects WHERE parent_id IS NULL
            ORDER BY priority ASC"""
        )

        total_hours = sum(p.get("time_allocation_hrs_week", 0) for p in projects)

        lines = [f"[PORTFOLIO: {len(projects)} projects, {total_hours}h/week total]"]
        for p in projects:
            name = p.get("name", "Unknown")
            ptype = p.get("type", "unknown")
            pri = p.get("priority", 5)
            status = p.get("status", "unknown")
            focus = p.get("current_focus") or "not set"
            hours = p.get("time_allocation_hrs_week", 0)
            updated = p.get("updated_at") or "unknown"
            lines.append(
                f"- P{pri}: {name} ({ptype}, {status}) — {hours}h/wk — "
                f"Focus: {focus} — Last updated: {updated}"
            )

        # Task completion stats
        task_stats = fetch_all(
            """SELECT p.name,
                   COUNT(CASE WHEN t.status = 'done' THEN 1 END) as done,
                   COUNT(CASE WHEN t.status IN ('todo','in_progress') THEN 1 END) as active
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            GROUP BY p.name"""
        )

        if task_stats:
            lines.append("\n[TASK COMPLETION]")
            for row in task_stats:
                name = row.get("name") or "General"
                done = row.get("done", 0)
                active = row.get("active", 0)
                lines.append(f"- {name}: {done} done, {active} active")

        # Knowledge density
        knowledge_stats = fetch_all(
            """SELECT p.name, COUNT(uk.id) as entries
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            GROUP BY p.name ORDER BY entries DESC"""
        )

        if knowledge_stats:
            lines.append("\n[KNOWLEDGE DENSITY]")
            for row in knowledge_stats:
                name = row.get("name") or "General"
                count = row.get("entries", 0)
                lines.append(f"- {name}: {count} entries")

        return "\n".join(lines)



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

# ============================================================================
# Legacy functions for backward compatibility
# ============================================================================

def generate_morning_briefing() -> str:
    """Generate and store the morning briefing. Returns the briefing text."""
    _llm = _get_llm_client()
    response = _llm.generate(
        prompt="Generate a concise morning briefing summarizing active projects, key tasks due today, and top priorities. Be specific and actionable.",
        system_prompt="You are an AI Chief of Staff. Provide a structured morning briefing for a solo operator managing multiple concurrent projects."
    )

    # Store as an insight
    execute(
        """INSERT INTO insights (type, content, severity, status)
           VALUES ('recommendation', ?, 'info', 'new')""",
        (f"[MORNING BRIEFING]\n{response}",),
    )

    return response


def run_pattern_analysis() -> str:
    """Run overnight pattern analysis. Returns the analysis text."""
    _llm = _get_llm_client()
    response = _llm.generate(
        prompt="Analyze patterns across active projects. Identify bottlenecks, stalled work, recurring themes, and cross-project dependencies. Surface actionable insights.",
        system_prompt="You are an AI Chief of Staff performing overnight pattern analysis across a portfolio of concurrent projects."
    )

    # Store as coaching insight
    execute(
        """INSERT INTO insights (type, content, severity, status)
           VALUES ('pattern', ?, 'info', 'new')""",
        (f"[PATTERN ANALYSIS]\n{response}",),
    )

    return response


def get_recent_insights(limit: int = 10, status: Optional[str] = None) -> list[Insight]:
    """Get recent insights, optionally filtered by status."""
    query = "SELECT * FROM insights"
    params: list = []

    if status:
        query += " WHERE status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = fetch_all(query, tuple(params))
    return [Insight.from_row(r) for r in rows]


def dismiss_insight(insight_id: int) -> None:
    execute("UPDATE insights SET status = 'dismissed' WHERE id = ?", (insight_id,))


def mark_insight_seen(insight_id: int) -> None:
    execute("UPDATE insights SET status = 'seen' WHERE id = ?", (insight_id,))


def mark_insight_acted(insight_id: int) -> None:
    execute("UPDATE insights SET status = 'acted_on' WHERE id = ?", (insight_id,))
