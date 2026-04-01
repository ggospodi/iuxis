"""
Connector status and management endpoints.

GET  /api/connectors/status          — all connectors status + recent runs
GET  /api/connectors/file-watcher/runs   — recent file watcher runs
POST /api/connectors/file-watcher/scan   — manually trigger inbox scan
POST /api/connectors/file-watcher/test   — test with a specific filename (dry run)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# Module-level reference to file watcher — set during app startup
_file_watcher = None

def set_file_watcher(watcher):
    global _file_watcher
    _file_watcher = watcher


@router.get("/status")
async def get_connector_status():
    """Summary status of all connectors."""
    inbox_dir = os.path.expanduser("~/iuxis-inbox")
    inbox_files = []
    if os.path.exists(inbox_dir):
        inbox_files = [
            f for f in os.listdir(inbox_dir)
            if os.path.isfile(os.path.join(inbox_dir, f))
            and not f.startswith('.')
        ]

    recent_runs = []
    if _file_watcher:
        recent_runs = _file_watcher.get_recent_runs(limit=5)

    return {
        "connectors": {
            "file_watcher": {
                "enabled": _file_watcher is not None,
                "inbox_path": inbox_dir,
                "files_pending": len(inbox_files),
                "pending_filenames": inbox_files,
            },
            "slack": {"enabled": False, "note": "planned v1.1"},
            "notion": {"enabled": False, "note": "planned v1.1"},
            "linear": {"enabled": False, "note": "planned v1.1"},
        },
        "recent_runs": recent_runs,
    }


@router.get("/file-watcher/runs")
async def get_file_watcher_runs(limit: int = 20):
    """Return recent file watcher sync runs."""
    if not _file_watcher:
        raise HTTPException(status_code=503, detail="File watcher not running")
    return {
        "runs": _file_watcher.get_recent_runs(limit=limit),
        "total": limit,
    }


@router.post("/file-watcher/scan")
async def trigger_inbox_scan():
    """
    Manually scan and process all files currently in the inbox.
    Useful for: processing files dropped while Iuxis was offline,
    or triggering a batch ingest.
    """
    if not _file_watcher:
        raise HTTPException(status_code=503, detail="File watcher not running")
    results = _file_watcher.process_inbox_now()
    total_entries = sum(r.get("entries_added", 0) for r in results)
    return {
        "files_processed": len(results),
        "total_entries_added": total_entries,
        "results": results,
    }


class TestParseRequest(BaseModel):
    filename: str

@router.post("/file-watcher/test-parse")
async def test_filename_parse(req: TestParseRequest):
    """
    Dry-run filename parsing — shows what project and category
    a filename would be routed to without processing anything.
    """
    from iuxis.connectors.inbox_parser import parse_filename
    project_slug, category_hint = parse_filename(req.filename)
    return {
        "filename": req.filename,
        "routed_to_project": project_slug,
        "category_hint": category_hint,
        "is_unassigned": project_slug == "_unassigned",
    }
