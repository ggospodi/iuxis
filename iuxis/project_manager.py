"""CRUD operations for projects."""
from __future__ import annotations

from typing import Optional
import json

from iuxis.db import fetch_all, fetch_one, execute, log_activity
from iuxis.models import Project, ProjectType, ProjectStatus


def create_project(
    name: str,
    type: str = "product",
    status: str = "active",
    priority: int = 3,
    description: str = "",
    time_allocation_hrs_week: float = 0.0,
    current_focus: str = "",
    obsidian_folder: str = "",
    tags: Optional[list[str]] = None,
    parent_id: Optional[int] = None,
) -> Project:
    """Create a new project and return it."""
    tags = tags or []
    pid = execute(
        """INSERT INTO projects
           (parent_id, name, type, status, priority, description,
            time_allocation_hrs_week, current_focus, obsidian_folder, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (parent_id, name, type, status, priority, description,
         time_allocation_hrs_week, current_focus, obsidian_folder, json.dumps(tags)),
    )
    log_activity("task_created", f"Project created: {name}", project_id=pid)
    return get_project(pid)


def get_project(project_id: int) -> Optional[Project]:
    row = fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    return Project.from_row(row) if row else None


def get_project_by_name(name: str) -> Optional[Project]:
    row = fetch_one("SELECT * FROM projects WHERE LOWER(name) = LOWER(?)", (name,))
    return Project.from_row(row) if row else None


def list_projects(
    status: Optional[str] = None,
    parent_id: Optional[int] = None,
    top_level_only: bool = False,
) -> list[Project]:
    """List projects with optional filters."""
    query = "SELECT * FROM projects WHERE 1=1 AND LOWER(name) != 'unassigned inbox'"
    params: list = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if parent_id is not None:
        query += " AND parent_id = ?"
        params.append(parent_id)
    if top_level_only:
        query += " AND parent_id IS NULL"

    query += " ORDER BY priority ASC, name ASC"
    rows = fetch_all(query, tuple(params))
    return [Project.from_row(r) for r in rows]


def update_project(project_id: int, **kwargs) -> Optional[Project]:
    """Update project fields. Pass only the fields you want to change."""
    allowed = {
        "name", "type", "status", "priority", "description",
        "time_allocation_hrs_week", "current_focus", "obsidian_folder",
        "tags", "parent_id",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_project(project_id)

    if "tags" in updates and isinstance(updates["tags"], list):
        updates["tags"] = json.dumps(updates["tags"])

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]

    execute(
        f"UPDATE projects SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        tuple(values),
    )

    if "priority" in updates:
        log_activity("project_priority_change",
                     f"Priority → {updates['priority']}", project_id=project_id)

    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    """Delete a project (and cascade-orphan children)."""
    # Re-parent children to NULL
    execute("UPDATE projects SET parent_id = NULL WHERE parent_id = ?", (project_id,))
    execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return True


def get_project_tree() -> list[dict]:
    """Return projects as a nested tree structure."""
    projects = list_projects()
    by_id = {p.id: {"project": p, "children": []} for p in projects}
    roots = []

    for p in projects:
        node = by_id[p.id]
        if p.parent_id and p.parent_id in by_id:
            by_id[p.parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


def get_all_projects_summary() -> str:
    """Get a compact text summary of all projects for Claude context."""
    projects = list_projects()
    if not projects:
        return "No projects registered yet."

    lines = ["PROJECTS:"]
    for p in projects:
        lines.append(f"  #{p.id}: {p.summary()}")
    return "\n".join(lines)
