"""Iuxis FastAPI backend."""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from iuxis_api.routes import projects, tasks, chat, knowledge, intelligence, ingestion, system, premium, connectors, work_pills, github, settings, onboarding

logger = logging.getLogger("iuxis_api")

app = FastAPI(
    title="Iuxis API",
    description="AI Chief of Staff — Local API",
    version="1.0.0"
)

# CORS for local Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    from iuxis import knowledge_manager
    from iuxis.scheduler import IuxisScheduler
    import sqlite3
    import os

    # Run database migrations
    try:
        # Initialize base schema first (if not exists)
        from iuxis.db import init_db
        init_db()
        logger.info("[Startup] Base schema initialized")

        db_path = os.path.join(os.path.dirname(__file__), "../data/iuxis.db")
        conn = sqlite3.connect(db_path)
        from migrations.run_migration import run_migration_003, run_migration_004, run_migration_005, run_migration_006, run_migration_007
        run_migration_003(conn)
        run_migration_004(conn)
        run_migration_005(conn)
        run_migration_006(conn)
        run_migration_007(conn)
        try:
            project_count = conn.execute("SELECT COUNT(*) FROM projects WHERE LOWER(name) != 'unassigned inbox'").fetchone()[0]
            if project_count == 0:
                logger.info("[Startup] Empty database — seeding demo projects...")
                from seed_demo import seed_demo
                seed_demo()
                logger.info("[Startup] Demo projects seeded.")
        except Exception as e:
            logger.warning(f"[Startup] Demo seed skipped: {e}")
        conn.close()
        logger.info("[Startup] Database migrations complete")
    except Exception as e:
        logger.error(f"[Startup] Migration error: {e}")

    # Build vector index from existing knowledge entries on first run
    try:
        vector_total = knowledge_manager.get_vector_store_total()
        if vector_total == 0:
            all_entries = knowledge_manager._fetch_all_for_indexing()
            if all_entries:
                logger.info(f"[Startup] Vector index empty, rebuilding from {len(all_entries)} entries...")
                knowledge_manager.rebuild_vector_index()
                logger.info("[Startup] Vector index ready.")
            else:
                logger.info("[Startup] No knowledge entries to index yet.")
        else:
            logger.info(f"[Startup] Vector index already populated with {vector_total} entries.")
    except Exception as e:
        logger.error(f"[Startup] Failed to initialize vector index: {e}")
        # Don't fail startup if vector index initialization fails

    # Start APScheduler
    try:
        scheduler = IuxisScheduler()
        scheduler.start()
        logger.info("[Startup] APScheduler started — nightly consolidation at 2:00 AM")
    except Exception as e:
        logger.error(f"[Startup] Failed to start scheduler: {e}")

    # File watcher — start after existing startup tasks (vector rebuild etc.)
    try:
        from iuxis.connectors.file_watcher import FileWatcherConnector
        from iuxis_api.routes.connectors import set_file_watcher

        file_watcher = FileWatcherConnector()
        file_watcher.start()
        # Process any files dropped while offline
        file_watcher.process_inbox_now()
        set_file_watcher(file_watcher)
        logger.info("[Startup] File watcher running — inbox: ~/iuxis-inbox/")
    except Exception as e:
        logger.warning(f"[Startup] File watcher failed to start: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    from iuxis.scheduler import get_scheduler

    try:
        scheduler = get_scheduler()
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("[Shutdown] APScheduler stopped")
    except Exception as e:
        logger.error(f"[Shutdown] Error stopping scheduler: {e}")

    # Graceful file watcher shutdown
    try:
        from iuxis_api.routes.connectors import _file_watcher
        if _file_watcher:
            _file_watcher.stop()
    except Exception:
        pass

# Register routes
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(intelligence.router, prefix="/api/intelligence", tags=["Intelligence"])
app.include_router(ingestion.router, prefix="/api/ingest", tags=["Ingestion"])
app.include_router(system.router, prefix="/api", tags=["System"])
app.include_router(premium.router, prefix="/api", tags=["Premium"])
app.include_router(connectors.router)
app.include_router(work_pills.router, prefix="/api", tags=["Work Pills"])
app.include_router(github.router, prefix="/api/github", tags=["GitHub"])
app.include_router(settings.router, prefix="/api", tags=["Settings"])
app.include_router(onboarding.router)

# WebSocket routes
from iuxis_api.websocket import chat_ws, dashboard_ws
app.include_router(chat_ws.router)
app.include_router(dashboard_ws.router)
