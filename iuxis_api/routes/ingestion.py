"""Ingestion endpoints."""
from fastapi import APIRouter, Depends
from iuxis_api.deps import get_db

router = APIRouter()

@router.post("/{slug}")
def ingest_project(slug: str, db=Depends(get_db)):
    """Trigger ingestion for a project."""
    try:
        from iuxis.ingestion_engine import ingest_project
        result = ingest_project(slug, db)
        return {"status": "ok", "slug": slug, "result": result}
    except Exception as e:
        return {"status": "error", "slug": slug, "error": str(e)}

@router.get("/pending")
def pending_files(db=Depends(get_db)):
    """Show files pending ingestion across all projects."""
    import os
    import glob

    projects_dir = os.path.expanduser("~/Desktop/iuxis/projects")
    pending = {}

    for project_dir in glob.glob(os.path.join(projects_dir, "*")):
        slug = os.path.basename(project_dir)
        raw_dir = os.path.join(project_dir, "raw")
        manifest_path = os.path.join(project_dir, ".ingested")

        if not os.path.isdir(raw_dir):
            continue

        # Read manifest
        ingested = set()
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                ingested = set(line.strip().split("|")[0] for line in f if line.strip())

        # Find new files
        raw_files = [f for f in os.listdir(raw_dir) if not f.startswith('.')]
        new_files = [f for f in raw_files if f not in ingested]

        if new_files:
            pending[slug] = new_files

    return {"pending": pending, "total_files": sum(len(f) for f in pending.values())}

@router.get("/stats")
def ingestion_stats(db=Depends(get_db)):
    """Ingestion statistics."""
    stats = {
        "projects": db.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
        "top_level_projects": db.execute("SELECT COUNT(*) FROM projects WHERE parent_id IS NULL").fetchone()[0],
        "tasks": db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
        "knowledge_entries": db.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0],
        "insights": db.execute("SELECT COUNT(*) FROM insights").fetchone()[0],
    }
    return stats
