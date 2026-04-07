"""
Iuxis Backup Module
====================
Local-first SQLite backup with automatic rotation and pre-destructive snapshots.

Storage: ~/.iuxis/backups/
Naming:  iuxis-{reason}-{label}-{YYYYMMDD-HHMMSS}.db

Reasons:
  - pre-delete  : Safety snapshot taken before a destructive operation. KEPT FOREVER.
  - scheduled   : Periodic backup from APScheduler. Rotated.
  - manual      : User-triggered via API or CLI. Rotated.
  - pre-commit  : Optional pre-commit snapshot. KEPT FOREVER.

Uses SQLite's online backup API — atomic and safe while the DB is in use.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from iuxis.db import get_db_path

logger = logging.getLogger(__name__)

BACKUP_DIR = Path.home() / ".iuxis" / "backups"

# Rotation policy
KEEP_SCHEDULED_RECENT = 7    # last 7 daily scheduled backups
KEEP_SCHEDULED_WEEKLY = 4    # plus 4 older weekly backups
KEEP_MANUAL = 10             # last 10 manual backups
# pre-delete and pre-commit backups are NEVER pruned automatically

VALID_REASONS = {"pre-delete", "scheduled", "manual", "pre-commit"}

# Filename pattern: iuxis-{reason}-{label}-{YYYYMMDD-HHMMSS}.db
# label is optional
_FILENAME_RE = re.compile(
    r"^iuxis-(?P<reason>pre-delete|pre-commit|scheduled|manual)"
    r"(?:-(?P<label>.+?))?"
    r"-(?P<ts>\d{8}-\d{6})\.db$"
)


@dataclass
class BackupInfo:
    path: Path
    reason: str
    label: str
    timestamp: datetime
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "filename": self.path.name,
            "path": str(self.path),
            "reason": self.reason,
            "label": self.label,
            "timestamp": self.timestamp.isoformat(),
            "size_bytes": self.size_bytes,
        }


def get_backup_dir() -> Path:
    return BACKUP_DIR


def _ensure_backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def _sanitize_label(label: str) -> str:
    """Strip filesystem-unfriendly chars from a label."""
    if not label:
        return ""
    safe = re.sub(r"[^a-zA-Z0-9_]+", "-", label.strip())
    safe = safe.strip("-")
    return safe[:60]


def create_backup(reason: str, label: str = "") -> Path:
    """
    Create an atomic SQLite backup using the online backup API.

    Args:
        reason: One of VALID_REASONS. Determines retention policy.
        label:  Optional descriptor (e.g. project name for pre-delete).

    Returns:
        Path to the created backup file.

    Raises:
        ValueError, FileNotFoundError, sqlite3.Error
    """
    if reason not in VALID_REASONS:
        raise ValueError(
            f"Invalid backup reason '{reason}'. Must be one of: {sorted(VALID_REASONS)}"
        )

    _ensure_backup_dir()
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Source database does not exist: {db_path}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_label = _sanitize_label(label)
    if safe_label:
        filename = f"iuxis-{reason}-{safe_label}-{timestamp}.db"
    else:
        filename = f"iuxis-{reason}-{timestamp}.db"

    target_path = BACKUP_DIR / filename

    src_conn = sqlite3.connect(str(db_path))
    dest_conn = sqlite3.connect(str(target_path))
    try:
        with dest_conn:
            src_conn.backup(dest_conn)
        size = target_path.stat().st_size
        logger.info(
            f"Backup created: {filename} ({size:,} bytes, reason={reason})"
        )
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        # Clean up partial file on failure
        if target_path.exists():
            try:
                target_path.unlink()
            except OSError:
                pass
        raise
    finally:
        src_conn.close()
        dest_conn.close()

    # Auto-prune for rotated reasons (best-effort, non-fatal)
    if reason in ("scheduled", "manual"):
        try:
            prune_backups(reason=reason)
        except Exception as e:
            logger.warning(f"Backup pruning failed (non-fatal): {e}")

    return target_path


def _parse_filename(path: Path) -> Optional[BackupInfo]:
    m = _FILENAME_RE.match(path.name)
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group("ts"), "%Y%m%d-%H%M%S")
    except ValueError:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return BackupInfo(
        path=path,
        reason=m.group("reason"),
        label=m.group("label") or "",
        timestamp=ts,
        size_bytes=size,
    )


def list_backups(reason: Optional[str] = None) -> List[BackupInfo]:
    """List all backups, newest first. Optionally filter by reason."""
    if not BACKUP_DIR.exists():
        return []
    backups: List[BackupInfo] = []
    for p in BACKUP_DIR.glob("iuxis-*.db"):
        info = _parse_filename(p)
        if info is None:
            continue
        if reason is not None and info.reason != reason:
            continue
        backups.append(info)
    backups.sort(key=lambda b: b.timestamp, reverse=True)
    return backups


def prune_backups(reason: str) -> int:
    """
    Apply rotation policy for a given reason. Returns count of files deleted.
    pre-delete and pre-commit are NEVER pruned by this function.
    """
    if reason in ("pre-delete", "pre-commit"):
        return 0

    backups = list_backups(reason=reason)
    keepers: set = set()

    if reason == "scheduled":
        # Keep the most recent N outright
        for b in backups[:KEEP_SCHEDULED_RECENT]:
            keepers.add(b.path)
        # Keep one per ISO week thereafter, up to KEEP_SCHEDULED_WEEKLY weeks
        seen_weeks: set = set()
        for b in backups[KEEP_SCHEDULED_RECENT:]:
            week_key = b.timestamp.strftime("%G-W%V")
            if week_key not in seen_weeks and len(seen_weeks) < KEEP_SCHEDULED_WEEKLY:
                seen_weeks.add(week_key)
                keepers.add(b.path)
    elif reason == "manual":
        for b in backups[:KEEP_MANUAL]:
            keepers.add(b.path)
    else:
        return 0

    deleted = 0
    for b in backups:
        if b.path not in keepers:
            try:
                b.path.unlink()
                deleted += 1
                logger.info(f"Pruned old backup: {b.path.name}")
            except OSError as e:
                logger.warning(f"Failed to prune {b.path.name}: {e}")
    return deleted


def restore_backup(backup_path: Path) -> None:
    """
    Restore a backup over the current database.

    Strategy:
      1. Take a 'pre-delete' safety snapshot of the CURRENT db (label=pre-restore)
      2. Atomically copy the backup contents into the live DB via SQLite backup API

    Args:
        backup_path: Path to the .db file to restore. MUST be inside BACKUP_DIR.

    Raises:
        FileNotFoundError, ValueError, sqlite3.Error
    """
    backup_path = Path(backup_path).resolve()
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Safety: only allow restores from inside BACKUP_DIR
    try:
        backup_path.relative_to(BACKUP_DIR.resolve())
    except ValueError:
        raise ValueError(
            f"Refusing to restore from outside backup directory: {backup_path}"
        )

    db_path = get_db_path()

    # 1. Pre-restore safety snapshot of current DB
    if db_path.exists():
        safety = create_backup(reason="pre-delete", label="pre-restore")
        logger.info(f"Pre-restore safety snapshot: {safety.name}")

    # 2. Atomic replace via SQLite online backup API (handles WAL/SHM cleanly)
    src_conn = sqlite3.connect(str(backup_path))
    dest_conn = sqlite3.connect(str(db_path))
    try:
        with dest_conn:
            src_conn.backup(dest_conn)
        logger.info(f"Restored database from {backup_path.name}")
    finally:
        src_conn.close()
        dest_conn.close()
