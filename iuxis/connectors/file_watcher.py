"""
FileWatcherConnector — monitors ~/iuxis-inbox/ for new files.

Triggers ingestion automatically when .md, .txt, or .pdf files
are dropped into the inbox folder.

Usage:
    watcher = FileWatcherConnector()
    watcher.start()   # non-blocking, runs in background thread
    watcher.stop()    # clean shutdown
"""

import os
import shutil
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from .inbox_parser import route_file
from .project_classifier import get_all_projects_for_classification

logger = logging.getLogger(__name__)

INBOX_DIR = os.path.expanduser("~/iuxis-inbox")
PROCESSED_DIR = os.path.join(INBOX_DIR, "processed")
FAILED_DIR = os.path.join(INBOX_DIR, "failed")
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}
DB_PATH = "data/iuxis.db"


class InboxEventHandler(FileSystemEventHandler):
    """Handles file system events in the inbox directory."""

    def __init__(self, connector: "FileWatcherConnector"):
        self.connector = connector
        self._processing: set = set()  # debounce: track files being processed

    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return
        filepath = event.src_path
        filename = os.path.basename(filepath)

        # Skip hidden files and non-supported extensions
        if filename.startswith('.'):
            return
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            logger.debug(f"Skipping unsupported file type: {filename}")
            return
        # Skip files in subdirectories (processed/, failed/)
        if os.path.dirname(filepath) != INBOX_DIR:
            return
        # Debounce: skip if already processing
        if filepath in self._processing:
            return

        self._processing.add(filepath)
        try:
            # Brief wait — ensure file write is complete before reading
            time.sleep(0.5)
            self.connector.process_file(filepath)
        finally:
            self._processing.discard(filepath)


class FileWatcherConnector:
    """
    Monitors ~/iuxis-inbox/ and triggers ingestion on new files.
    Runs in a background thread — non-blocking.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.observer: Optional[Observer] = None
        self._ensure_directories()
        self._ensure_source_registered()

    def _ensure_directories(self):
        os.makedirs(INBOX_DIR, exist_ok=True)
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        os.makedirs(FAILED_DIR, exist_ok=True)
        logger.info(f"[FileWatcher] Inbox: {INBOX_DIR}")

    def _ensure_source_registered(self):
        """Register file_watcher source in sync_sources if not exists."""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            existing = conn.execute(
                "SELECT id FROM sync_sources WHERE source_type = 'file_watcher'"
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO sync_sources (source_type, config, sync_interval_minutes, enabled)
                       VALUES ('file_watcher', ?, 0, 1)""",
                    [f'{{"inbox_path": "{INBOX_DIR}"}}']
                )
                conn.commit()
                logger.info("[FileWatcher] Registered file_watcher source in DB")
            conn.close()
        except Exception as e:
            logger.warning(f"[FileWatcher] Could not register source: {e}")

    def start(self):
        """Start the file watcher in background thread."""
        event_handler = InboxEventHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, INBOX_DIR, recursive=False)
        self.observer.start()
        logger.info(f"[FileWatcher] Started — watching {INBOX_DIR}")

    def stop(self):
        """Stop the file watcher cleanly."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("[FileWatcher] Stopped")

    def process_file(self, filepath: str) -> dict:
        """
        Process a single file from the inbox.

        Steps:
        1. Parse filename → project slug + category hint
        2. Copy to projects/<slug>/raw/
        3. Run ingestion engine on the file
        4. Move original to processed/ or failed/
        5. Write sync_runs record

        Returns dict with status, entries_added, project_slug
        """
        filename = os.path.basename(filepath)
        run_id = self._start_sync_run(filename)

        logger.info(f"[FileWatcher] Processing: {filename}")

        try:
            # Step 1: Route file using new smart routing
            projects = get_all_projects_for_classification()
            routing = route_file(filepath, projects)

            project_id = routing['project_id']
            route_method = routing['route_method']
            confidence = routing['confidence']

            logger.info(f"[FileWatcher] Routed via {route_method}: '{filename}' → project_id={project_id} (confidence={confidence:.2f})")

            # Determine project slug for destination and ingestion
            if project_id is None:
                project_slug = "_unassigned"
                project_id = self._ensure_unassigned_project()
            else:
                # Get slug from project_id
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                row = conn.execute("SELECT name FROM projects WHERE id = ?", [project_id]).fetchone()
                conn.close()
                if row and row[0]:
                    project_slug = row[0].lower().replace(" ", "-")
                else:
                    # Fallback: use lowercased name with hyphens
                    project_slug = routing['project_name'].lower().replace(' ', '-') if routing['project_name'] else "_unassigned"

            # Step 2: Copy to project raw directory
            dest_path = self._get_destination_path(project_slug, filename)
            shutil.copy2(filepath, dest_path)
            logger.info(f"[FileWatcher] Copied to: {dest_path}")

            # Step 3: Run ingestion
            entries_added = self._run_ingestion(dest_path, project_slug)
            logger.info(f"[FileWatcher] Ingested {entries_added} entries from {filename}")

            # Step 4: Move to processed
            processed_path = os.path.join(
                PROCESSED_DIR,
                f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{filename}"
            )
            shutil.move(filepath, processed_path)

            # Step 5: Update sync run
            self._complete_sync_run(run_id, "success", entries_added, project_slug, dest_path)

            return {
                "status": "success",
                "project_slug": project_slug,
                "entries_added": entries_added,
                "destination": dest_path,
            }

        except Exception as e:
            logger.error(f"[FileWatcher] Failed to process {filename}: {e}", exc_info=True)

            # Move to failed/
            try:
                failed_path = os.path.join(FAILED_DIR, filename)
                shutil.move(filepath, failed_path)
            except Exception:
                pass

            self._complete_sync_run(run_id, "error", 0, None, None, str(e))
            return {"status": "error", "error": str(e)}

    def _get_destination_path(self, project_slug: str, filename: str) -> str:
        """
        Build the destination path within the projects directory.

        For known projects: ~/Desktop/iuxis/projects/<slug>/raw/<filename>
        For unassigned:     ~/Desktop/iuxis/projects/_unassigned/raw/<filename>
        """
        base_dir = os.path.expanduser("~/Desktop/iuxis/projects")
        dest_dir = os.path.join(base_dir, project_slug, "raw")
        os.makedirs(dest_dir, exist_ok=True)
        return os.path.join(dest_dir, filename)

    def _run_ingestion(self, filepath: str, project_slug: str) -> int:
        """
        Run the existing ingestion engine on a single file.
        Returns number of knowledge entries added.
        """
        try:
            from iuxis.ingestion_engine import ingest_project, extract_knowledge_from_checkpoint

            # Count entries before
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            before = conn.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0]
            
            # Get project_id from slug
            row = conn.execute(
                "SELECT id FROM projects WHERE LOWER(name) LIKE ?", [f"%{project_slug}%"]
            ).fetchone()
            conn.close()

            if not row:
                project_id = self._ensure_unassigned_project()
                # For unassigned files, extract directly — don't call ingest_project
                extract_knowledge_from_checkpoint(filepath, project_id)
            else:
                project_id = row[0]
                # Run full ingestion pipeline on the matched project
                ingest_project(project_slug, force=False)

            # Count entries after
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            after = conn.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0]
            conn.close()

            return after - before

        except Exception as e:
            logger.error(f"[FileWatcher] Ingestion failed: {e}", exc_info=True)
            raise

    def _ensure_unassigned_project(self) -> int:
        """Create or fetch the _unassigned catch-all project."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        row = conn.execute(
            "SELECT id FROM projects WHERE name = 'Unassigned Inbox'"
        ).fetchone()
        if row:
            conn.close()
            return row[0]
        conn.execute(
            """INSERT INTO projects (name, description, status, priority)
               VALUES ('Unassigned Inbox',
                       'Files dropped to inbox without a recognized project',
                       'active', 3)"""
        )
        conn.commit()
        project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return project_id

    def _start_sync_run(self, filename: str) -> int:
        """Insert a sync_runs record, return its ID."""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            source = conn.execute(
                "SELECT id FROM sync_sources WHERE source_type = 'file_watcher'"
            ).fetchone()
            source_id = source[0] if source else None
            conn.execute(
                """INSERT INTO sync_runs (source_id, source_type, filename, status)
                   VALUES (?, 'file_watcher', ?, 'running')""",
                [source_id, filename]
            )
            conn.commit()
            run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return run_id
        except Exception:
            return -1

    def _complete_sync_run(
        self, run_id: int, status: str, entries_added: int,
        project_slug: Optional[str], dest_path: Optional[str],
        error_message: Optional[str] = None
    ):
        """Update sync_runs record on completion."""
        if run_id < 0:
            return
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute(
                """UPDATE sync_runs
                   SET completed_at = CURRENT_TIMESTAMP,
                       status = ?, entries_added = ?,
                       project_slug = ?, destination_path = ?,
                       error_message = ?
                   WHERE id = ?""",
                [status, entries_added, project_slug, dest_path, error_message, run_id]
            )
            # Update last_synced_at on the source
            conn.execute(
                """UPDATE sync_sources SET last_synced_at = CURRENT_TIMESTAMP
                   WHERE source_type = 'file_watcher'"""
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[FileWatcher] Could not update sync run {run_id}: {e}")

    def get_recent_runs(self, limit: int = 20) -> list:
        """Return recent sync runs for the API status endpoint."""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            rows = conn.execute(
                """SELECT id, filename, project_slug, entries_added, status,
                          started_at, completed_at, error_message
                   FROM sync_runs
                   WHERE source_type = 'file_watcher'
                   ORDER BY started_at DESC LIMIT ?""",
                [limit]
            ).fetchall()
            conn.close()
            return [
                {
                    "id": r[0], "filename": r[1], "project_slug": r[2],
                    "entries_added": r[3], "status": r[4],
                    "started_at": r[5], "completed_at": r[6],
                    "error_message": r[7],
                }
                for r in rows
            ]
        except Exception:
            return []

    def process_inbox_now(self) -> list:
        """
        Manually scan and process any existing files in inbox.
        Called at startup to catch files dropped while Iuxis was offline.
        Returns list of result dicts.
        """
        results = []
        for filename in os.listdir(INBOX_DIR):
            filepath = os.path.join(INBOX_DIR, filename)
            if not os.path.isfile(filepath):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            result = self.process_file(filepath)
            results.append({**result, "filename": filename})
        if results:
            logger.info(f"[FileWatcher] Startup scan processed {len(results)} files")
        return results
