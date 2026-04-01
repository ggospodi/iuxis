"""
Premium feature API routes.
All endpoints require active premium license (stubbed to True in development).
"""

from fastapi import APIRouter, HTTPException, Query
from iuxis.premium.license import is_premium
from iuxis.premium.consolidation import (
    run_consolidation_pass,
    get_consolidation_history,
    fetch_recent_chat_knowledge
)
import logging

logger = logging.getLogger("iuxis.routes.premium")
router = APIRouter()


def _check_premium():
    if not is_premium():
        raise HTTPException(
            status_code=402,
            detail={
                "error": "premium_required",
                "message": "This feature requires Iuxis Premium. Visit iuxis.ai/pricing"
            }
        )


@router.post("/premium/consolidation/run")
async def trigger_consolidation():
    """
    Manually trigger a memory consolidation pass.
    Same logic as the nightly job — consolidates chat-sourced entries from last 7 days.
    """
    _check_premium()
    logger.info("[API] Manual consolidation triggered")
    result = run_consolidation_pass(trigger="manual")
    return result


@router.get("/premium/consolidation/history")
async def get_consolidation_history_endpoint(
    limit: int = Query(10, ge=1, le=50)
):
    """Get history of consolidation runs."""
    _check_premium()
    history = get_consolidation_history(limit=limit)
    return {"runs": history, "count": len(history)}


@router.get("/premium/consolidation/pending")
async def get_pending_entries(
    days: int = Query(7, ge=1, le=30)
):
    """Preview what entries would be consolidated in the next run."""
    _check_premium()
    entries = fetch_recent_chat_knowledge(days=days)

    # Group by project for preview
    by_project = {}
    for e in entries:
        pid = e.get("project_id")
        by_project.setdefault(pid, []).append(e)

    preview = [
        {
            "project_id": pid,
            "entry_count": len(group),
            "will_consolidate": len(group) >= 3,
            "entries": [{"id": e["id"], "category": e["category"], "content": e["content"][:80]} for e in group]
        }
        for pid, group in by_project.items()
    ]

    return {
        "total_pending": len(entries),
        "days_lookback": days,
        "projects": preview
    }


@router.get("/premium/status")
async def premium_status():
    """Check premium license status and scheduled job status."""
    from iuxis.scheduler import get_scheduler

    scheduler = get_scheduler()
    job = scheduler.get_job("nightly_consolidation")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return {
        "premium_active": is_premium(),
        "stub_mode": False,
        "scheduler_running": scheduler.running,
        "consolidation_job": {
            "scheduled": job is not None,
            "next_run": next_run,
        }
    }
