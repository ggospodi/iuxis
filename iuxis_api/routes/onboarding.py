"""Onboarding endpoints — workspace reset for first-time users."""

from fastapi import APIRouter
import sqlite3
import os
import shutil

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("/reset")
async def reset_workspace():
    """
    Wipe all demo data and reset to clean state.
    Called when user says "Ready to start" in chat.
    """
    from iuxis.db import get_connection
    conn = get_connection()

    try:
        # Temporarily disable foreign key constraints
        conn.execute("PRAGMA foreign_keys = OFF")
        # Delete ALL data — not just demo-tagged, everything
        # This is a full workspace reset

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
        # Get all projects with their parent relationships
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
        # Get the repo root directory (parent of iuxis_api)
        projects_dir = os.path.join(os.path.dirname(__file__), "..", "..", "projects")
        projects_dir = os.path.abspath(projects_dir)

        for demo_dir in ["novabrew", "orbit-marketing", "example-project"]:
            dir_path = os.path.join(projects_dir, demo_dir)
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)

        return {
            "status": "reset_complete",
            "message": "Workspace cleared. Ready for your projects."
        }

    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        # Re-enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()
