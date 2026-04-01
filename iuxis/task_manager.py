"""CRUD operations for tasks."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
import json

from iuxis.db import fetch_all, fetch_one, execute, log_activity
from iuxis.models import Task


def create_task(
    title: str,
    project_id: Optional[int] = None,
    description: str = "",
    status: str = "todo",
    priority: int = 3,
    due_date: Optional[date] = None,
    estimated_hours: Optional[float] = None,
    created_by: str = "user",
    ai_rationale: str = "",
    tags: Optional[list[str]] = None,
) -> Task:
    """Create a new task and return it."""
    tags = tags or []
    due_str = due_date.isoformat() if due_date else None
    tid = execute(
        """INSERT INTO tasks
           (project_id, title, description, status, priority,
            due_date, estimated_hours, created_by, ai_rationale, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (project_id, title, description, status, priority,
         due_str, estimated_hours, created_by, ai_rationale, json.dumps(tags)),
    )
    log_activity("task_created", f"Task created: {title}", project_id=project_id, task_id=tid)
    return get_task(tid)


def get_task(task_id: int) -> Optional[Task]:
    row = fetch_one(
        """SELECT t.*, p.name as project_name
           FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
           WHERE t.id = ?""",
        (task_id,),
    )
    return Task.from_row(row) if row else None


def list_tasks(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    due_before: Optional[date] = None,
    priority_max: Optional[int] = None,
    limit: int = 50,
) -> list[Task]:
    """List tasks with optional filters."""
    query = """SELECT t.*, p.name as project_name
               FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
               WHERE 1=1"""
    params: list = []

    if project_id is not None:
        query += " AND t.project_id = ?"
        params.append(project_id)
    if status:
        query += " AND t.status = ?"
        params.append(status)
    if due_before:
        query += " AND t.due_date <= ?"
        params.append(due_before.isoformat())
    if priority_max:
        query += " AND t.priority <= ?"
        params.append(priority_max)

    query += " ORDER BY t.priority ASC, t.due_date ASC NULLS LAST, t.created_at DESC"
    query += f" LIMIT {limit}"

    rows = fetch_all(query, tuple(params))
    return [Task.from_row(r) for r in rows]


def get_todays_tasks() -> list[Task]:
    """Get tasks due today or currently in progress."""
    today = date.today().isoformat()
    rows = fetch_all(
        """SELECT t.*, p.name as project_name
           FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
           WHERE (t.due_date <= ? AND t.status NOT IN ('done', 'cancelled'))
              OR t.status = 'in_progress'
           ORDER BY t.priority ASC, t.due_date ASC""",
        (today,),
    )
    return [Task.from_row(r) for r in rows]


def get_upcoming_tasks(days: int = 7) -> list[Task]:
    """Get tasks due within the next N days."""
    from datetime import timedelta
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    rows = fetch_all(
        """SELECT t.*, p.name as project_name
           FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
           WHERE t.due_date <= ? AND t.status NOT IN ('done', 'cancelled')
           ORDER BY t.due_date ASC, t.priority ASC""",
        (cutoff,),
    )
    return [Task.from_row(r) for r in rows]


def update_task(task_id: int, **kwargs) -> Optional[Task]:
    """Update task fields."""
    allowed = {
        "title", "description", "status", "priority", "due_date",
        "estimated_hours", "actual_hours", "ai_rationale", "tags", "project_id",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_task(task_id)

    # Handle special types
    if "tags" in updates and isinstance(updates["tags"], list):
        updates["tags"] = json.dumps(updates["tags"])
    if "due_date" in updates and isinstance(updates["due_date"], date):
        updates["due_date"] = updates["due_date"].isoformat()

    old_task = get_task(task_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]

    execute(
        f"UPDATE tasks SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        tuple(values),
    )

    # Track completion
    if updates.get("status") == "done":
        execute(
            "UPDATE tasks SET completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        log_activity("task_completed", f"Task completed: {old_task.title if old_task else ''}",
                     project_id=old_task.project_id if old_task else None, task_id=task_id)
    elif "status" in updates:
        log_activity("task_status_change", f"Status → {updates['status']}",
                     project_id=old_task.project_id if old_task else None, task_id=task_id)

    return get_task(task_id)


def complete_task(task_id: int) -> Optional[Task]:
    return update_task(task_id, status="done")


def delete_task(task_id: int) -> bool:
    execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return True


def get_all_tasks_summary(include_done: bool = False) -> str:
    """Compact text summary for Claude context."""
    status_filter = None if include_done else None
    query = """SELECT t.*, p.name as project_name
               FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
               WHERE 1=1"""
    if not include_done:
        query += " AND t.status NOT IN ('done', 'cancelled')"
    query += " ORDER BY t.priority ASC, t.due_date ASC NULLS LAST LIMIT 30"

    rows = fetch_all(query)
    tasks = [Task.from_row(r) for r in rows]

    if not tasks:
        return "No active tasks."

    lines = ["ACTIVE TASKS:"]
    for t in tasks:
        proj = f" [{t.project_name}]" if t.project_name else ""
        lines.append(f"  #{t.id}{proj}: {t.summary()}")
    return "\n".join(lines)
