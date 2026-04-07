"""Backup management endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from iuxis import backup as backup_mod

router = APIRouter(prefix="/api/backup", tags=["backup"])


class CreateBackupRequest(BaseModel):
    reason: str = "manual"
    label: str = ""


class RestoreBackupRequest(BaseModel):
    filename: str  # backup filename inside BACKUP_DIR (no path traversal)


@router.post("/create")
def create_backup(req: CreateBackupRequest):
    """Create a new backup. Default reason is 'manual'."""
    try:
        path = backup_mod.create_backup(reason=req.reason, label=req.label)
        return {"success": True, "filename": path.name, "path": str(path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")


@router.get("/list")
def list_backups(reason: Optional[str] = None):
    """List all backups. Optional ?reason=scheduled|manual|pre-delete|pre-commit"""
    backups = backup_mod.list_backups(reason=reason)
    return {
        "count": len(backups),
        "backup_dir": str(backup_mod.get_backup_dir()),
        "backups": [b.to_dict() for b in backups],
    }


@router.post("/restore")
def restore_backup(req: RestoreBackupRequest):
    """
    Restore a backup by filename. The filename must exist inside the backup
    directory. A pre-restore safety snapshot of the current DB is taken
    automatically before the restore.
    """
    backup_dir = backup_mod.get_backup_dir().resolve()
    candidate = (backup_dir / req.filename).resolve()
    # Path traversal guard
    try:
        candidate.relative_to(backup_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    if not candidate.exists():
        raise HTTPException(
            status_code=404, detail=f"Backup not found: {req.filename}"
        )
    try:
        backup_mod.restore_backup(candidate)
        return {"success": True, "restored_from": candidate.name}
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")
