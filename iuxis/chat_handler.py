"""Chat message routing, command parsing, and action execution."""
from __future__ import annotations

import re
import math
import logging
from datetime import date, datetime
from typing import Optional, Dict, Any

from iuxis.db import execute, fetch_all, log_activity
from iuxis.context_assembler import assemble_context
from iuxis.llm_client import LLMClient as _LLMClient
from iuxis.project_manager import (
    create_project, get_project, get_project_by_name, update_project,
)
from iuxis.task_manager import (
    create_task, get_task, update_task, complete_task,
)
from iuxis.models import ChatMessage

logger = logging.getLogger("iuxis.chat_handler")

# Import importance from Stream A if available, else use inline version (consolidate later)
try:
    from iuxis.importance import compute_importance
except ImportError:
    # Stream A not yet complete — use inline version (consolidate later)
    def compute_importance(category, content, source="chat", confidence="high", pinned=False):
        base = 0.35
        category_bonus = {"decision": 0.30, "fact": 0.18, "context": 0.08, "task": 0.15}.get(category, 0.10)
        source_bonus = {"manual": 0.10, "chat": 0.06, "ingestion": 0.08}.get(source, 0.05)
        confidence_bonus = {"high": 0.08, "medium": 0.04, "low": 0.0}.get(confidence, 0.04)
        length_bonus = min(0.10, math.log1p(len(content.split())) / 35.0)
        pin_bonus = 0.35 if pinned else 0.0
        return float(min(1.0, base + category_bonus + source_bonus + confidence_bonus + length_bonus + pin_bonus))


# ---------------------------------------------------------------------------
# /remember Command and Save Signal Detection
# ---------------------------------------------------------------------------

REMEMBER_COMMANDS = ["/remember", "/rem", "/save"]

# Patterns that suggest a decision or notable preference is being stated
SAVE_SIGNAL_PATTERNS = [
    r"\blet'?s go with\b",
    r"\bwe'?ll use\b",
    r"\bi'?ve decided\b",
    r"\bmoving forward\b",
    r"\bprioritize\b",
    r"\bdeprioritize\b",
    r"\bnew approach\b",
    r"\bchanging the plan\b",
    r"\bactually[,\s]",
    r"\bcorrection[:\s]",
    r"\binstead[,\s]",
    r"\bscrapping\b",
    r"\bpivot(ing)?\b",
    r"\bdecision[:\s]",
    r"\bgoing to\b.{0,30}\binstead\b",
]
_SAVE_PATTERN_RE = re.compile("|".join(SAVE_SIGNAL_PATTERNS), re.IGNORECASE)



_llm_singleton: Optional[_LLMClient] = None

def _get_llm_client() -> _LLMClient:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = _LLMClient()
    return _llm_singleton

def _infer_category(content: str) -> str:
    """
    Infer knowledge category from content text.
    Simple keyword matching — no LLM call.
    """
    lower = content.lower()
    if any(w in lower for w in ["decided", "decision", "going with", "will use", "chose", "choosing"]):
        return "decision"
    if any(w in lower for w in ["risk", "concern", "worry", "careful", "danger", "issue"]):
        return "risk"
    if any(w in lower for w in ["task", "todo", "need to", "must", "action item", "by "]):
        return "workflow_rule"
    if any(w in lower for w in ["%", "revenue", "users", "metric", "kpi", "target", "goal"]):
        return "metric"
    if any(w in lower for w in ["architecture", "system", "infra", "database", "api", "stack"]):
        return "project_context"
    if any(w in lower for w in ["compliance", "legal", "hipaa", "gdpr", "regulation"]):
        return "compliance"
    return "fact"  # Default


def _detect_save_signal(user_message: str, assistant_response: str) -> Optional[Dict]:
    """
    Detect if the exchange contains a decision or notable knowledge worth saving.
    Uses regex only — no LLM call. Returns None if nothing notable detected.
    """
    combined = user_message + " " + assistant_response

    if not _SAVE_PATTERN_RE.search(combined):
        return None

    # Prefer the more specific of the two texts
    # User message for stated preferences/decisions; assistant for confirmed summaries
    if _SAVE_PATTERN_RE.search(user_message):
        text = user_message
    else:
        text = assistant_response

    # Truncate to reasonable length
    text = text[:600].strip()

    # Suggest a category
    suggested_category = _infer_category(text)

    return {
        "text": text,
        "suggested_category": suggested_category,
        "source": "chat",
    }


# ---------------------------------------------------------------------------
# Chat History
# ---------------------------------------------------------------------------

def save_message(role: str, content: str, tokens: int = 0) -> None:
    execute(
        "INSERT INTO chat_history (role, content, tokens_used) VALUES (?, ?, ?)",
        (role, content, tokens),
    )


def get_chat_history(limit: int = 20) -> list[dict]:
    rows = fetch_all(
        "SELECT role, content FROM chat_history ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return list(reversed(rows))


def clear_chat_history() -> None:
    execute("DELETE FROM chat_history")


# ---------------------------------------------------------------------------
# System Prompt for Chief of Staff
# ---------------------------------------------------------------------------

CHIEF_OF_STAFF_PROMPT = """You are the Chief of Staff for a technology executive managing 12-15 concurrent projects. Your job is to optimize his time, surface insights, and coach him toward maximum productivity.

Your principles:
- Be direct, specific, and actionable. Never be vague.
- When suggesting priorities, give concrete reasons tied to deadlines, dependencies, or impact.
- When coaching, reference specific patterns from activity data.
- When creating tasks or updating projects, output structured commands (see below).
- Keep responses concise — the user is busy.

When the user asks you to create or modify data, respond with both:
1. A human-readable confirmation of what you're doing
2. A command block that the system will parse and execute

Command format:
---COMMAND---
action: create_task
project: Project Name or ID
title: Task title here
description: Optional description
priority: 1-5 (default 3)
due_date: YYYY-MM-DD (optional)
estimated_hours: 2.0 (optional)
---END_COMMAND---

---COMMAND---
action: update_task
task_id: 123
status: todo|in_progress|blocked|done|cancelled
priority: 1-5 (optional)
---END_COMMAND---

---COMMAND---
action: complete_task
task_id: 123
---END_COMMAND---

---COMMAND---
action: create_project
name: Project Name
type: product|research|learning|advisory|consulting|company
priority: 1-5 (default 3)
description: Project description
time_allocation_hrs_week: 4.0 (optional)
current_focus: What we're working on now (optional)
parent: Parent project name or ID (optional)
---END_COMMAND---

---COMMAND---
action: update_project
project_id: 123
priority: 1-5 (optional)
current_focus: Updated focus (optional)
status: active|paused|blocked|monitoring (optional)
---END_COMMAND---

---COMMAND---
action: update_priority
task_id: 123 (optional)
project_id: 456 (optional)
priority: 1-5
---END_COMMAND---

---COMMAND---
action: delete_project
project_name: (required) exact project name to delete
confirm: (required) must be "yes" — always ask the user to confirm before deleting
---END_COMMAND---

Multiple commands can be included in a single response. The system will execute them and confirm.

Today's date: {today}
Current time: {now}
"""


# ---------------------------------------------------------------------------
# Command Parser
# ---------------------------------------------------------------------------

def parse_commands(response: str) -> list[dict]:
    """Extract command blocks from Claude's response.

    Returns list of parsed commands as dicts.
    """
    commands = []
    pattern = r'-*COMMAND-*\s*(.*?)\s*-*END_COMMAND-*'
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)

    for match in matches:
        cmd = {}
        lines = match.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or ':' not in line:
                continue
            key, _, value = line.partition(':')
            key = key.strip().lower().replace(' ', '_')
            value = value.strip()
            if value:
                cmd[key] = value
        if 'action' in cmd:
            commands.append(cmd)

    return commands


def strip_commands(response: str) -> str:
    """Remove command blocks from response text for display."""
    pattern = r'-*COMMAND-*\s*.*?\s*-*END_COMMAND-*'
    return re.sub(pattern, '', response, flags=re.DOTALL | re.IGNORECASE).strip()


# ---------------------------------------------------------------------------
# Command Execution
# ---------------------------------------------------------------------------

def execute_command(cmd: dict) -> str:
    """Execute a parsed command and return a status message."""
    action = cmd.get("action", "")

    try:
        if action == "create_task":
            return _exec_create_task(cmd)
        elif action == "update_task":
            return _exec_update_task(cmd)
        elif action == "complete_task":
            return _exec_complete_task(cmd)
        elif action == "create_project":
            return _exec_create_project(cmd)
        elif action == "update_project":
            return _exec_update_project(cmd)
        elif action == "update_priority":
            return _exec_update_priority(cmd)
        elif action == "delete_project":
            return _exec_delete_project(cmd)
        else:
            return f"⚠️ Unknown action: {action}"
    except Exception as e:
        return f"❌ Error executing {action}: {e}"


def _resolve_project_id(name_or_id: str) -> Optional[int]:
    """Resolve a project name or ID to an integer ID."""
    if not name_or_id:
        return None
    if name_or_id.isdigit():
        return int(name_or_id)
    proj = get_project_by_name(name_or_id)
    return proj.id if proj else None


def _exec_create_task(cmd: dict) -> str:
    project_id = None
    if "project" in cmd:
        project_id = _resolve_project_id(cmd["project"])
        if project_id is None:
            return f"⚠️ Project not found: {cmd['project']}"

    due = None
    if "due_date" in cmd and cmd["due_date"]:
        try:
            due = date.fromisoformat(cmd["due_date"])
        except ValueError:
            pass

    est_hours = None
    if "estimated_hours" in cmd:
        try:
            est_hours = float(cmd["estimated_hours"])
        except ValueError:
            pass

    priority = 3
    if "priority" in cmd:
        try:
            priority = int(cmd["priority"])
        except ValueError:
            pass

    task = create_task(
        title=cmd.get("title", "Untitled task"),
        project_id=project_id,
        description=cmd.get("description", ""),
        priority=priority,
        due_date=due,
        estimated_hours=est_hours,
        created_by="ai",
        ai_rationale=cmd.get("rationale", ""),
    )
    return f"✅ Task created: #{task.id} — {task.title}\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"


def _exec_update_task(cmd: dict) -> str:
    task_id_str = cmd.get("task_id")
    if not task_id_str:
        return "⚠️ No task_id provided"

    try:
        task_id = int(task_id_str)
    except ValueError:
        return f"⚠️ Invalid task_id: {task_id_str}"

    updates = {}
    if "status" in cmd:
        updates["status"] = cmd["status"]
    if "priority" in cmd:
        try:
            updates["priority"] = int(cmd["priority"])
        except ValueError:
            pass
    if "title" in cmd:
        updates["title"] = cmd["title"]
    if "description" in cmd:
        updates["description"] = cmd["description"]
    if "due_date" in cmd:
        try:
            updates["due_date"] = date.fromisoformat(cmd["due_date"])
        except ValueError:
            pass
    if "estimated_hours" in cmd:
        try:
            updates["estimated_hours"] = float(cmd["estimated_hours"])
        except ValueError:
            pass

    task = update_task(task_id, **updates)
    if task:
        return f"✅ Task #{task_id} updated: {task.title} → {task.status.value}\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"
    return f"⚠️ Task #{task_id} not found"


def _exec_complete_task(cmd: dict) -> str:
    task_id_str = cmd.get("task_id")
    if not task_id_str:
        return "⚠️ No task_id provided"

    try:
        task_id = int(task_id_str)
    except ValueError:
        return f"⚠️ Invalid task_id: {task_id_str}"

    task = complete_task(task_id)
    if task:
        return f"✅ Task #{task_id} completed: {task.title}\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"
    return f"⚠️ Task #{task_id} not found"


def _exec_create_project(cmd: dict) -> str:
    parent_id = None
    if "parent" in cmd:
        parent_id = _resolve_project_id(cmd["parent"])

    priority = 3
    if "priority" in cmd:
        try:
            priority = int(cmd["priority"])
        except ValueError:
            pass

    time_alloc = 0.0
    if "time_allocation_hrs_week" in cmd:
        try:
            time_alloc = float(cmd["time_allocation_hrs_week"])
        except ValueError:
            pass

    proj = create_project(
        name=cmd.get("name", "Untitled"),
        type=cmd.get("type", "product"),
        status=cmd.get("status", "active"),
        priority=priority,
        description=cmd.get("description", ""),
        time_allocation_hrs_week=time_alloc,
        current_focus=cmd.get("current_focus", ""),
        parent_id=parent_id,
    )
    return f"✅ Project created: #{proj.id} — {proj.name}\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"


def _exec_update_project(cmd: dict) -> str:
    project_id_str = cmd.get("project_id")
    if not project_id_str:
        return "⚠️ No project_id provided"

    try:
        project_id = int(project_id_str)
    except ValueError:
        return f"⚠️ Invalid project_id: {project_id_str}"

    updates = {}
    if "priority" in cmd:
        try:
            updates["priority"] = int(cmd["priority"])
        except ValueError:
            pass
    if "current_focus" in cmd:
        updates["current_focus"] = cmd["current_focus"]
    if "status" in cmd:
        updates["status"] = cmd["status"]
    if "description" in cmd:
        updates["description"] = cmd["description"]
    if "time_allocation_hrs_week" in cmd:
        try:
            updates["time_allocation_hrs_week"] = float(cmd["time_allocation_hrs_week"])
        except ValueError:
            pass

    proj = update_project(project_id, **updates)
    if proj:
        return f"✅ Project #{project_id} updated: {proj.name}\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"
    return f"⚠️ Project #{project_id} not found"


def _exec_update_priority(cmd: dict) -> str:
    """Update priority for either a task or project."""
    priority_str = cmd.get("priority")
    if not priority_str:
        return "⚠️ No priority value provided"

    try:
        priority = int(priority_str)
        if not 1 <= priority <= 5:
            return "⚠️ Priority must be between 1 and 5"
    except ValueError:
        return f"⚠️ Invalid priority: {priority_str}"

    # Check for task_id
    if "task_id" in cmd:
        try:
            task_id = int(cmd["task_id"])
            task = update_task(task_id, priority=priority)
            if task:
                return f"✅ Task #{task_id} priority updated to P{priority}\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"
            return f"⚠️ Task #{task_id} not found"
        except ValueError:
            return f"⚠️ Invalid task_id: {cmd['task_id']}"

    # Check for project_id
    if "project_id" in cmd:
        try:
            project_id = int(cmd["project_id"])
            proj = update_project(project_id, priority=priority)
            if proj:
                return f"✅ Project #{project_id} priority updated to P{priority}\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"
            return f"⚠️ Project #{project_id} not found"
        except ValueError:
            return f"⚠️ Invalid project_id: {cmd['project_id']}"

    return "⚠️ Must provide either task_id or project_id"


def _exec_delete_project(cmd: dict) -> str:
    """Delete a project and all its sub-projects, tasks, and knowledge entries."""
    import sqlite3
    from iuxis.db import get_connection

    project_name = cmd.get("project_name", "")
    confirm = cmd.get("confirm", "").lower()

    if confirm != "yes":
        return "⚠️ Delete requires confirmation. Please confirm you want to delete this project."

    # Look up project by name
    project_rows = fetch_all(
        "SELECT id, name FROM projects WHERE LOWER(name) = LOWER(?)", (project_name,)
    )
    if not project_rows:
        return f"❌ Project '{project_name}' not found."

    project_id = project_rows[0]["id"]
    project_name_actual = project_rows[0]["name"]

    # Get all sub-project IDs (recursive)
    all_ids = [project_id]
    sub_ids = fetch_all(
        "SELECT id FROM projects WHERE parent_id = ?", (project_id,)
    )
    all_ids.extend([s["id"] for s in sub_ids])

    # Also get sub-sub-projects (one more level)
    for sub_id in [s["id"] for s in sub_ids]:
        subsub = fetch_all(
            "SELECT id FROM projects WHERE parent_id = ?", (sub_id,)
        )
        all_ids.extend([s["id"] for s in subsub])

    placeholders = ','.join(['?'] * len(all_ids))

    # Use a dedicated connection to manage foreign key constraints
    try:
        conn = get_connection()

        # Temporarily disable foreign key constraints
        conn.execute("PRAGMA foreign_keys = OFF")

        # Delete from all child tables first (in dependency order)
        conn.execute(f"DELETE FROM tasks WHERE project_id IN ({placeholders})", all_ids)
        conn.execute(f"DELETE FROM user_knowledge WHERE project_id IN ({placeholders})", all_ids)
        conn.execute(f"DELETE FROM schedule_blocks WHERE project_id IN ({placeholders})", all_ids)
        conn.execute(f"DELETE FROM activity_log WHERE project_id IN ({placeholders})", all_ids)

        # Delete insights (no foreign key, but uses project_id in related_project_ids JSON)
        conn.execute("DELETE FROM insights WHERE related_project_ids LIKE ?", (f'%{project_id}%',))

        # Delete sub-projects first, then parent (children before parents)
        for pid in reversed(all_ids):
            conn.execute("DELETE FROM projects WHERE id = ?", (pid,))

        conn.commit()

        # Re-enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

        return f"✅ Project '{project_name_actual}' and all its sub-projects, tasks, and knowledge entries have been deleted.\n\n*Refresh your dashboard (Cmd+R) to see the changes.*"

    except Exception as e:
        logger.error(f"[ChatHandler] Failed to delete project {project_name}: {e}")
        return f"❌ Failed to delete project: {e}"


# ---------------------------------------------------------------------------
# ChatHandler Class
# ---------------------------------------------------------------------------

class ChatHandler:
    """Main chat handler that processes user messages and executes commands."""

    def __init__(self, channel_id: Optional[int] = None):
        """Initialize chat handler.

        Args:
            channel_id: Optional channel ID for filtering chat history
        """
        self.channel_id = channel_id
        self._last_assistant_response = None  # For /remember last

    def _handle_remember_command(
        self, message: str, command: str, project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Handle /remember [text] command — save to user_knowledge."""

        content = message[len(command):].strip()

        # /remember last → save last assistant response
        if content.lower() == "last":
            content = self._last_assistant_response
            if not content:
                return {
                    "response": "⚠️ No previous response to save. Try `/remember [text]` with explicit content.",
                    "command": "remember",
                    "success": False
                }

        if not content:
            return {
                "response": (
                    "💾 **Save to knowledge base**\n\n"
                    "Usage:\n"
                    "• `/remember [text]` — save specific text\n"
                    "• `/remember last` — save my last response\n\n"
                    "Example: `/remember We decided to use PostgreSQL for the HDV production database`"
                ),
                "command": "remember",
                "success": False
            }

        # Infer category from content (simple heuristic, no LLM call)
        category = _infer_category(content)

        # Compute importance
        importance = compute_importance(
            category=category,
            content=content,
            source="chat",
            confidence="high",
        )

        # Save to user_knowledge
        try:
            from iuxis.knowledge_manager import add_knowledge

            entry_id = add_knowledge(
                category=category,
                content=content,
                source="chat",
                confidence="high",
                project_id=project_id,
                status="approved",
            )

            logger.info(f"[ChatHandler] Saved knowledge entry {entry_id} from /remember (importance={importance:.2f})")

            return {
                "response": (
                    f"✅ **Saved to knowledge base**\n\n"
                    f"**Category:** {category}\n"
                    f"**Importance:** {importance:.2f}\n"
                    f"**Entry ID:** {entry_id}\n\n"
                    f"_{content[:120]}{'...' if len(content) > 120 else ''}_\n\n"
                    f"View in **Knowledge Explorer** → filter by source: chat"
                ),
                "command": "remember",
                "success": True,
                "saved_entry": {
                    "id": entry_id,
                    "category": category,
                    "content": content,
                    "importance": importance
                }
            }
        except Exception as e:
            logger.error(f"[ChatHandler] Failed to save knowledge entry: {e}")
            return {
                "response": f"⚠️ Failed to save: {e}",
                "command": "remember",
                "success": False
            }

    def _handle_onboarding_reset(self, user_message: str) -> Dict[str, Any]:
        """Handle 'Ready to start' — wipe demo data and guide user."""
        import os
        import shutil
        import sqlite3
        from iuxis.db import get_connection

        # Save the user's message first
        save_message("user", user_message)

        # Perform the reset directly (no HTTP call to avoid deadlock)
        try:
            conn = get_connection()

            # Temporarily disable foreign key constraints
            conn.execute("PRAGMA foreign_keys = OFF")

            # Get all project IDs except Unassigned Inbox
            project_rows = conn.execute(
                "SELECT id FROM projects WHERE LOWER(name) != 'unassigned inbox'"
            ).fetchall()
            project_ids = [row[0] for row in project_rows]

            if project_ids:
                placeholders = ','.join(['?'] * len(project_ids))

                # Delete in dependency order: tasks first, then knowledge, then projects
                conn.execute(f"DELETE FROM tasks WHERE project_id IN ({placeholders})", project_ids)
                conn.execute(f"DELETE FROM user_knowledge WHERE project_id IN ({placeholders})", project_ids)

                # Delete schedule_blocks if table exists
                try:
                    conn.execute(f"DELETE FROM schedule_blocks WHERE project_id IN ({placeholders})", project_ids)
                except sqlite3.OperationalError:
                    pass

            # Delete insights (no foreign key dependency)
            conn.execute("DELETE FROM insights")

            # Delete chat_history
            conn.execute("DELETE FROM chat_history")

            # Delete knowledge_relations if table exists
            try:
                conn.execute("DELETE FROM knowledge_relations")
            except sqlite3.OperationalError:
                pass  # Table may not exist

            # Delete activity_log if table exists
            try:
                conn.execute("DELETE FROM activity_log")
            except sqlite3.OperationalError:
                pass

            # Delete projects in reverse order (children before parents)
            if project_ids:
                # Get sub-sub-projects first (level 2)
                level2 = conn.execute("""
                    SELECT p2.id FROM projects p2
                    INNER JOIN projects p1 ON p2.parent_id = p1.id
                    INNER JOIN projects p0 ON p1.parent_id = p0.id
                    WHERE LOWER(p2.name) != 'unassigned inbox'
                """).fetchall()

                # Get sub-projects (level 1)
                level1 = conn.execute("""
                    SELECT p1.id FROM projects p1
                    INNER JOIN projects p0 ON p1.parent_id = p0.id
                    WHERE LOWER(p1.name) != 'unassigned inbox'
                    AND p1.id NOT IN (SELECT id FROM projects WHERE id IN ({}))
                """.format(','.join(str(r[0]) for r in level2) if level2 else '0')).fetchall()

                # Get top-level projects (level 0)
                level0 = conn.execute("""
                    SELECT id FROM projects
                    WHERE parent_id IS NULL
                    AND LOWER(name) != 'unassigned inbox'
                """).fetchall()

                # Delete in order: level2 -> level1 -> level0
                for level in [level2, level1, level0]:
                    for row in level:
                        conn.execute("DELETE FROM projects WHERE id = ?", (row[0],))

            conn.commit()

            # Remove demo project directories
            # Get the repo root directory (two levels up from iuxis/)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            projects_dir = os.path.join(current_dir, "..", "projects")
            projects_dir = os.path.abspath(projects_dir)

            for demo_dir in ["novabrew", "orbit-marketing", "example-project"]:
                dir_path = os.path.join(projects_dir, demo_dir)
                if os.path.exists(dir_path):
                    shutil.rmtree(dir_path)

            # Re-enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON")
            conn.close()

        except Exception as e:
            error_msg = f"❌ Error resetting workspace: {e}"
            save_message("assistant", error_msg, 0)
            logger.error(f"[ChatHandler] Onboarding reset failed: {e}")
            return {
                "response": error_msg,
                "save_signal": None,
                "saved_entry": None,
                "command": "onboarding_reset",
            }

        # Return the guided walkthrough
        walkthrough = """✅ **Workspace cleared!** You're starting fresh.

**Refresh your browser (Cmd+R) to see the clean dashboard.**

Let's set up your first project. Here's how:

**Step 1 — Create a project:**
Tell me about something you're working on. For example:
> "Create a project called Acme Redesign — it's a product, P1 priority, about 20 hours per week. We're rebuilding the marketing website."

**Step 2 — Add context:**
Your inbox folder is at ~/iuxis-inbox/ (created automatically). Drop files there and I'll read and route them to the right project. You can change this location in config.yaml under paths.inbox.

**Tip:** Name files as `projectname-topic-YYYYMMDD.md` for best results — e.g., `acme-redesign-kickoff-20260401.md`. This helps me route files to the right project instantly.

**Step 3 — Start working:**
Once you have a project set up, try:
- "What should I work on today?"
- "Generate my morning briefing"
- "Add a task: Review the Q2 roadmap"

**You can create as many projects as you need.** I work best when I can see across all of them — that's how I spot dependencies, conflicts, and opportunities.

What's the first project you'd like to set up?"""

        # Save the walkthrough message to chat history
        save_message("assistant", walkthrough, 0)

        return {
            "response": walkthrough,
            "save_signal": None,
            "saved_entry": None,
            "command": "onboarding_reset",
        }

    def handle_knowledge_query(self, user_message: str) -> Optional[str]:
        """Handle knowledge base queries."""
        patterns = [
            r"what do you know about (.+)",
            r"knowledge about (.+)",
            r"tell me about (.+)",
            r"what.*know.*about (.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, user_message.lower())
            if match:
                query = match.group(1).strip().rstrip('?')
                return self._search_knowledge(query)
        return None

    def _search_knowledge(self, query: str) -> str:
        """Search knowledge base and format results."""
        from iuxis.knowledge_manager import search_knowledge
        from iuxis.context_assembler import detect_project_from_message

        # Try project-specific search first
        project_id = detect_project_from_message(query)
        if project_id:
            entries = search_knowledge(query, project_id=project_id, limit=10)
        else:
            entries = search_knowledge(query, limit=10)

        if not entries:
            return f"I don't have any knowledge entries matching '{query}'. Try ingesting more project files."

        lines = [f"**Knowledge entries matching '{query}':**\n"]
        for entry in entries:
            category = entry.get("category", "unknown")
            content = entry.get("content", "")
            source_file = entry.get("source_file")
            lines.append(f"- **[{category}]** {content}")
            if source_file:
                lines.append(f"  _Source: {source_file}_")

        lines.append(f"\n_{len(entries)} entries found._")
        return "\n".join(lines)

    def handle_knowledge_stats(self, user_message: str) -> Optional[str]:
        """Show knowledge base statistics."""
        if not any(kw in user_message.lower() for kw in ['knowledge stats', 'knowledge summary', 'how much knowledge']):
            return None

        rows = fetch_all(
            """SELECT p.name, COUNT(uk.id) as count,
                   GROUP_CONCAT(DISTINCT uk.category) as categories
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            WHERE uk.status = 'approved'
            GROUP BY uk.project_id
            ORDER BY count DESC"""
        )

        total = sum(r.get("count", 0) for r in rows)
        lines = [f"**Knowledge Base: {total} entries across {len(rows)} projects**\n"]
        for r in rows:
            proj_name = r.get("name") or "General"
            count = r.get("count", 0)
            categories = r.get("categories") or "none"
            lines.append(f"- **{proj_name}:** {count} entries ({categories})")

        return "\n".join(lines)

    def handle_ingest_command(self, user_message: str) -> Optional[str]:
        """Trigger ingestion for a project."""
        patterns = [
            r"ingest.*(?:files?\s+)?(?:for\s+)?(.+)",
            r"process files?\s+(?:for\s+)?(.+)",
            r"scan files?\s+(?:for\s+)?(.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, user_message.lower())
            if match:
                project_query = match.group(1).strip()
                from iuxis.context_assembler import detect_project_from_message

                project_id = detect_project_from_message(project_query)
                if not project_id:
                    return f"I couldn't find a project matching '{project_query}'. Check project names with 'show projects'."

                # Get project name and derive slug for ingestion
                name_rows = fetch_all(
                    "SELECT name FROM projects WHERE id = ?", (project_id,)
                )
                if not name_rows or not name_rows[0].get("name"):
                    return f"Project found but has no name."

                from iuxis.context_assembler import project_name_to_slug
                slug = project_name_to_slug(name_rows[0]["name"])

                try:
                    from iuxis.ingestion_engine import ingest_project
                    result = ingest_project(slug)
                    if 'error' in result:
                        return f"❌ Ingestion failed for {slug}: {result['error']}"
                    files_processed = result.get('files_processed', 0)
                    knowledge_added = result.get('knowledge_added', 0)
                    return f"✅ Ingested **{slug}**: {files_processed} files processed, {knowledge_added} knowledge entries extracted."
                except Exception as e:
                    return f"❌ Ingestion failed for {slug}: {str(e)}"

        return None

    def handle_briefing_command(self, user_message: str) -> Optional[str]:
        """Handle briefing generation/display."""
        keywords = ['briefing', 'morning briefing', 'generate briefing', 'daily briefing']
        if not any(kw in user_message.lower() for kw in keywords):
            return None

        from iuxis.briefing_engine import BriefingEngine
        engine = BriefingEngine()

        # Check for existing today's briefing
        if 'generate' in user_message.lower() or 'new' in user_message.lower():
            result = engine.generate_morning_briefing()
            return result['briefing_text']

        # Try to show existing
        existing = engine.get_latest_briefing()
        if existing:
            return existing

        # Generate new one
        result = engine.generate_morning_briefing()
        return result['briefing_text']

    def handle_schedule_command(self, user_message: str) -> Optional[str]:
        """Handle schedule generation/display."""
        keywords = ['schedule', 'generate schedule', 'today schedule', 'time blocks']
        if not any(kw in user_message.lower() for kw in keywords):
            return None

        from iuxis.schedule_generator import ScheduleGenerator
        from datetime import date
        gen = ScheduleGenerator()

        if 'generate' in user_message.lower() or 'new' in user_message.lower():
            blocks = gen.generate_daily_schedule()
            return gen.format_schedule(blocks)

        # Show existing schedule
        blocks_raw = fetch_all(
            """SELECT p.name, sb.start_time, sb.end_time, sb.block_type, sb.status
            FROM schedule_blocks sb
            LEFT JOIN projects p ON sb.project_id = p.id
            WHERE sb.date = ?
            ORDER BY sb.start_time ASC""",
            (date.today().isoformat(),)
        )

        if blocks_raw:
            blocks = [{
                'project_name': b.get("name") or "General",
                'task_title': '',
                'start_time': b.get("start_time", "00:00"),
                'end_time': b.get("end_time", "00:00"),
                'date': date.today().isoformat()
            } for b in blocks_raw]
            return gen.format_schedule(blocks)

        # No schedule, generate one
        blocks = gen.generate_daily_schedule()
        return gen.format_schedule(blocks)

    def handle_insights_command(self, user_message: str) -> Optional[str]:
        """Handle insight generation."""
        keywords = ['generate insights', 'analyze projects', 'cross-project analysis']
        if not any(kw in user_message.lower() for kw in keywords):
            return None

        from iuxis.insight_engine import InsightEngine
        engine = InsightEngine()
        insights = engine.generate_insights()

        if not insights:
            return "No new insights generated. Everything looks balanced."

        lines = [f"**Generated {len(insights)} new insights:**\n"]
        for i in insights:
            severity_icon = {'info': 'ℹ️', 'warning': '⚠️', 'critical': '🚨'}.get(i.get('severity', 'info'), 'ℹ️')
            lines.append(f"{severity_icon} **[{i.get('type', 'observation')}]** {i['content']}")

        return "\n".join(lines)

    def handle_message(self, user_message: str, project_id: Optional[int] = None) -> Dict[str, Any]:
        """Process a user message through the full chat pipeline.

        Steps:
        0. Check for onboarding reset trigger (before everything else)
        1. Check for /remember commands (intercept before saving)
        2. Save user message to chat_history
        3. Check Tier 1 commands (knowledge queries, stats, ingestion)
        4. Assemble context from database
        5. Call Claude API with system prompt
        6. Parse command blocks from response
        7. Execute commands (create_task, update_task, etc.)
        8. Strip command blocks from response
        9. Detect save signals
        10. Save assistant response
        11. Log to activity_log

        Args:
            user_message: The user's input message
            project_id: Optional project context for /remember

        Returns:
            Dict with 'response', 'save_signal', 'saved_entry', 'command' keys
        """
        # 0. Check for onboarding trigger FIRST (before any other processing)
        lower_msg = user_message.lower().strip()
        ready_phrases = ["ready to start", "let's go", "clear demo", "start fresh", "reset workspace", "i'm ready"]
        if any(phrase in lower_msg for phrase in ready_phrases):
            return self._handle_onboarding_reset(user_message)

        # 1. Check for /remember commands (before saving message)
        stripped = user_message.strip()
        for cmd in REMEMBER_COMMANDS:
            if stripped.lower().startswith(cmd):
                result = self._handle_remember_command(
                    message=stripped,
                    command=cmd,
                    project_id=project_id
                )
                # Save the /remember command and response to history
                save_message("user", user_message)
                save_message("assistant", result["response"], 0)
                return result

        # 1. Save user message
        save_message("user", user_message)
        log_activity("chat_query", user_message[:100])

        # 2. Tier 1: Direct commands (no LLM needed)
        response = (
            self.handle_knowledge_query(user_message) or
            self.handle_knowledge_stats(user_message) or
            self.handle_ingest_command(user_message) or
            self.handle_briefing_command(user_message) or
            self.handle_schedule_command(user_message) or
            self.handle_insights_command(user_message) or
            None
        )

        if response:
            save_message("assistant", response, 0)
            return {"response": response, "save_signal": None, "saved_entry": None, "command": None}

        # 3. Assemble context
        context_result = assemble_context(user_message=user_message, channel_id=self.channel_id)
        context = context_result["context_text"]

        # Optional: Log retrieval metadata for debugging
        logging.debug(
            f"[ChatHandler] Context: type={context_result['query_type']} "
            f"strategy={context_result['strategy_used']} "
            f"entity_states={context_result['entity_states_included']}"
        )

        # 4. Build system prompt with current date/time
        now = datetime.now()
        system_prompt = CHIEF_OF_STAFF_PROMPT.format(
            today=date.today().isoformat(),
            now=now.strftime("%H:%M"),
        )

        # 5. Call Claude API
        try:
            _llm = _get_llm_client()
            full_prompt = context + "\n\n" + user_message if context else user_message
            response_text = _llm.generate(
                prompt=full_prompt,
                system_prompt=system_prompt,
            )
            # Strip any CJK character leakage from Qwen
            import re as _re
            response_text = _re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]+', '', response_text).strip()
            tokens = len(response_text.split())
        except Exception as e:
            error_msg = f"❌ Claude API error: {e}"
            save_message("assistant", error_msg, 0)
            return {"response": error_msg, "save_signal": None, "saved_entry": None, "command": None}

        # 6. Parse commands from response
        commands = parse_commands(response_text)

        # 7. Execute commands
        command_results = []
        for cmd in commands:
            result = execute_command(cmd)
            command_results.append(result)

        # 8. Strip command blocks from response
        display_response = strip_commands(response_text)

        # 9. Build final response with command results
        if command_results:
            display_response += "\n\n---\n**Actions executed:**\n" + "\n".join(command_results)

        # 10. Store for /remember last
        self._last_assistant_response = display_response

        # 11. Detect save signal
        save_signal = _detect_save_signal(user_message, display_response)

        # 12. Save assistant response
        save_message("assistant", display_response, tokens)

        return {
            "response": display_response,
            "save_signal": save_signal,
            "saved_entry": None,
            "command": None,
        }
