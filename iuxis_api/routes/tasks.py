"""Task endpoints."""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from iuxis_api.deps import get_db

router = APIRouter()

@router.get("")
def list_tasks(
    status: Optional[str] = None,
    project_id: Optional[int] = None,
    priority: Optional[int] = None,
    db=Depends(get_db)
):
    """Get tasks with optional filters."""
    query = "SELECT t.*, p.name as project_name FROM tasks t LEFT JOIN projects p ON t.project_id = p.id WHERE 1=1"
    params = []

    if status:
        query += " AND t.status = ?"
        params.append(status)
    if project_id:
        query += " AND (t.project_id = ? OR t.project_id IN (SELECT id FROM projects WHERE parent_id = ?))"
        params.extend([project_id, project_id])
    if priority:
        query += " AND t.priority = ?"
        params.append(priority)

    query += " ORDER BY t.priority ASC, t.due_date ASC"
    rows = db.execute(query, params).fetchall()
    columns = [desc[0] for desc in db.execute(query.replace("WHERE 1=1", "WHERE 0=1"), []).description] if rows else []

    # Simpler approach
    tasks = []
    for row in rows:
        task_cols = [desc[0] for desc in db.execute("PRAGMA table_info(tasks)").fetchall()]
        # Use raw column access
        pass

    # Just return raw data with column names from description
    cursor = db.execute(
        "SELECT t.*, p.name as project_name FROM tasks t LEFT JOIN projects p ON t.project_id = p.id ORDER BY t.priority ASC",
    )
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    tasks = [dict(zip(columns, row)) for row in rows]

    # Apply filters in Python for simplicity
    if status:
        tasks = [t for t in tasks if t.get('status') == status]
    if project_id:
        tasks = [t for t in tasks if t.get('project_id') == project_id]
    if priority:
        tasks = [t for t in tasks if t.get('priority') == priority]

    return {"tasks": tasks, "total": len(tasks)}

@router.get("/today")
def todays_tasks(db=Depends(get_db)):
    """Get today's prioritized tasks."""
    from iuxis.priority_engine import PriorityEngine
    engine = PriorityEngine()
    ranked = engine.rank_tasks_for_today()
    return {"tasks": ranked, "total": len(ranked)}

@router.post("")
def create_task(task: dict, db=Depends(get_db)):
    """Create a new task."""
    cursor = db.execute("""
        INSERT INTO tasks (title, project_id, priority, status, estimated_hours, due_date, tags, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task['title'],
        task.get('project_id'),
        task.get('priority', 3),
        task.get('status', 'todo'),
        task.get('estimated_hours'),
        task.get('due_date'),
        task.get('tags'),
        task.get('created_by', 'user')
    ))
    db.commit()
    return {"status": "created", "task_id": cursor.lastrowid}

@router.patch("/{task_id}")
def update_task(task_id: int, updates: dict, db=Depends(get_db)):
    """Update task fields."""
    allowed = ['title', 'status', 'priority', 'estimated_hours', 'due_date', 'tags']
    sets = []
    values = []
    for key, val in updates.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)

    if not sets:
        return {"error": "No valid fields to update"}

    values.append(task_id)
    db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)
    db.commit()
    return {"status": "updated", "task_id": task_id}

@router.delete("/{task_id}")
def delete_task(task_id: int, db=Depends(get_db)):
    """Delete a task."""
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return {"status": "deleted", "task_id": task_id}
