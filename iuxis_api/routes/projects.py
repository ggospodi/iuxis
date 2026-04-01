"""Project endpoints."""
from fastapi import APIRouter, Depends
from iuxis_api.deps import get_db

router = APIRouter()

@router.get("")
def list_projects(db=Depends(get_db)):
    """Get all projects with hierarchy."""
    rows = db.execute("""
        SELECT id, name, type, status, priority, description, current_focus,
               time_allocation_hrs_week, parent_id, obsidian_folder, tags, created_at, updated_at
        FROM projects WHERE LOWER(name) != 'unassigned inbox' ORDER BY priority ASC, name ASC
    """).fetchall()

    columns = ['id', 'name', 'type', 'status', 'priority', 'description',
               'current_focus', 'time_allocation_hrs_week', 'parent_id', 'obsidian_folder',
               'tags', 'created_at', 'updated_at']
    projects = [dict(zip(columns, row)) for row in rows]

    # Build hierarchy
    top_level = [p for p in projects if p['parent_id'] is None]
    for parent in top_level:
        parent['sub_projects'] = [p for p in projects if p['parent_id'] == parent['id']]

    return {"projects": top_level, "total": len(projects)}

@router.get("/{project_id}")
def get_project(project_id: int, db=Depends(get_db)):
    """Get single project with sub-projects and tasks."""
    row = db.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not row:
        return {"error": "Project not found"}

    columns = [desc[0] for desc in db.execute("SELECT * FROM projects LIMIT 0").description]
    project = dict(zip(columns, row))

    # Sub-projects
    subs = db.execute(
        "SELECT * FROM projects WHERE parent_id = ?", (project_id,)
    ).fetchall()
    project['sub_projects'] = [dict(zip(columns, s)) for s in subs]

    # Tasks
    task_rows = db.execute(
        "SELECT * FROM tasks WHERE project_id = ? OR project_id IN (SELECT id FROM projects WHERE parent_id = ?)",
        (project_id, project_id)
    ).fetchall()
    if task_rows:
        task_cols = [desc[0] for desc in db.execute("SELECT * FROM tasks LIMIT 0").description]
        project['tasks'] = [dict(zip(task_cols, t)) for t in task_rows]
    else:
        project['tasks'] = []

    # Knowledge count
    kcount = db.execute(
        "SELECT COUNT(*) FROM user_knowledge WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    project['knowledge_count'] = kcount

    return project

@router.patch("/{project_id}")
def update_project(project_id: int, updates: dict, db=Depends(get_db)):
    """Update project fields."""
    allowed = ['current_focus', 'priority', 'status', 'description', 'time_allocation_hrs_week']
    sets = []
    values = []
    for key, val in updates.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)

    if not sets:
        return {"error": "No valid fields to update"}

    values.append(project_id)
    db.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", values)
    db.commit()
    return {"status": "updated", "project_id": project_id}
