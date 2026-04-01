"""Intelligence endpoints — briefing, schedule, insights."""
from fastapi import APIRouter, Depends, BackgroundTasks
from iuxis_api.deps import get_db

router = APIRouter()

# --- Briefing ---

@router.post("/briefing/generate")
def generate_briefing(background_tasks: BackgroundTasks, db=Depends(get_db)):
    """Generate Today's Focus. Returns immediately with the briefing text."""
    from iuxis.briefing_engine import BriefingEngine
    engine = BriefingEngine()
    result = engine.generate_morning_briefing()
    # Unwrap briefing_text so frontend gets a plain string at result.briefing
    return {"status": "ok", "briefing": result.get("briefing_text", "")}

@router.get("/briefing/latest")
def latest_briefing(db=Depends(get_db)):
    """Get today's most recent briefing."""
    from iuxis.briefing_engine import BriefingEngine
    engine = BriefingEngine()
    briefing = engine.get_latest_briefing()
    if briefing:
        return {"briefing": briefing, "exists": True}
    return {"briefing": None, "exists": False}

# --- Schedule ---

@router.post("/schedule/generate")
def generate_schedule(db=Depends(get_db)):
    """Generate daily schedule."""
    from iuxis.schedule_generator import ScheduleGenerator
    gen = ScheduleGenerator()
    blocks = gen.generate_daily_schedule()
    return {"blocks": blocks, "total": len(blocks)}

@router.get("/schedule/today")
def todays_schedule(db=Depends(get_db)):
    """Get today's schedule blocks."""
    from datetime import date
    rows = db.execute("""
        SELECT sb.id, p.name as project_name, sb.start_time, sb.end_time,
               sb.block_type, sb.status, sb.date
        FROM schedule_blocks sb
        LEFT JOIN projects p ON sb.project_id = p.id
        WHERE sb.date = ?
        ORDER BY sb.start_time ASC
    """, (date.today().isoformat(),)).fetchall()

    columns = ['id', 'project_name', 'start_time', 'end_time', 'block_type', 'status', 'date']
    blocks = [dict(zip(columns, row)) for row in rows]
    return {"blocks": blocks, "total": len(blocks)}

# --- Insights ---

@router.post("/insights/generate")
def generate_insights(db=Depends(get_db)):
    """Trigger cross-project insight generation."""
    from iuxis.insight_engine import InsightEngine
    engine = InsightEngine()
    insights = engine.generate_insights()
    return {"insights": insights, "total": len(insights)}

@router.get("/insights")
def list_insights(status: str = None, limit: int = 20, db=Depends(get_db)):
    """Get insights with optional status filter."""
    query = "SELECT * FROM insights WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor = db.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    insights = [dict(zip(columns, row)) for row in rows]

    return {"insights": insights, "total": len(insights)}

@router.patch("/insights/{insight_id}")
def update_insight(insight_id: int, updates: dict, db=Depends(get_db)):
    """Update insight status (dismiss, act on, etc.)."""
    if 'status' in updates:
        db.execute("UPDATE insights SET status = ? WHERE id = ?", (updates['status'], insight_id))
        db.commit()
    return {"status": "updated", "insight_id": insight_id}
