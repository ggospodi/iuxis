"""
work_pills.py — LLM-extracted work-type pills for project cards.

Endpoint: GET /api/projects/work-pills
- Calls Qwen once for all top-level projects
- Returns 3 specific 2+ word pills per project
- Maps each pill to a color cluster for frontend rendering
- Cached in memory for the session (cleared on backend restart)

Drop this file at: ~/Desktop/iuxis/iuxis_api/routes/work_pills.py
Then register in iuxis_api/main.py:
    from iuxis_api.routes.work_pills import router as work_pills_router
    app.include_router(work_pills_router, prefix="/api")
"""

import json
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from iuxis_api.deps import get_db
from iuxis.llm_client import LLMClient

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory cache: { project_id: [{ label, color, bg }] }
_pills_cache: dict = {}

# Color cluster map — pill label is matched to closest cluster by the LLM
COLOR_CLUSTERS = {
    "build":    {"color": "#93C5FD", "bg": "rgba(59,130,246,0.15)"},
    "polish":   {"color": "#FCD34D", "bg": "rgba(245,158,11,0.15)"},
    "deploy":   {"color": "#6EE7B7", "bg": "rgba(52,211,153,0.15)"},
    "fix":      {"color": "#FB923C", "bg": "rgba(234,88,12,0.15)"},
    "test":     {"color": "#A1A1AA", "bg": "rgba(113,113,122,0.15)"},
    "research": {"color": "#67E8F9", "bg": "rgba(6,182,212,0.15)"},
    "outreach": {"color": "#C4B5FD", "bg": "rgba(139,92,246,0.15)"},
    "strategy": {"color": "#F9A8D4", "bg": "rgba(236,72,153,0.15)"},
}


def _build_prompt(projects: list[dict]) -> str:
    project_lines = "\n".join(
        f"- ID {p['id']} | {p['name']}: {p.get('current_focus') or p.get('description') or 'No focus set'}"
        for p in projects
    )
    cluster_names = ", ".join(COLOR_CLUSTERS.keys())
    return f"""/no_think

You are classifying work types for a solo operator's project dashboard.

For each project below, generate EXACTLY 3 work-type pills.

Rules:
- Each pill MUST be 2–5 words (no single words)
- Be specific and actionable, not generic. "Fix Compliance Gaps" not "Fix Issues"
- Each pill must also specify which color cluster it belongs to, chosen from: {cluster_names}
- Choose the closest cluster — if ambiguous, make a definitive choice
- Return ONLY valid JSON, no explanation

Projects:
{project_lines}

Return this exact JSON structure:
{{
  "pills": [
    {{
      "project_id": <int>,
      "items": [
        {{"label": "<2-5 word pill>", "cluster": "<cluster name>"}},
        {{"label": "<2-5 word pill>", "cluster": "<cluster name>"}},
        {{"label": "<2-5 word pill>", "cluster": "<cluster name>"}}
      ]
    }}
  ]
}}"""


@router.get("/project-pills")
async def get_work_pills(db=Depends(get_db), refresh: bool = False):
    """
    Returns LLM-generated work-type pills for all top-level projects.
    Cached in memory until backend restarts or ?refresh=true is passed.
    """
    global _pills_cache

    if _pills_cache and not refresh:
        return {"pills": _pills_cache, "cached": True}

    # Fetch top-level projects
    rows = db.execute(
        """
        SELECT id, name, current_focus, description
        FROM projects
        WHERE parent_id IS NULL AND status != 'archived'
        ORDER BY priority ASC, name ASC
        """
    ).fetchall()

    if not rows:
        return {"pills": {}, "cached": False}

    projects = [
        {"id": r[0], "name": r[1], "current_focus": r[2], "description": r[3]}
        for r in rows
    ]

    # Call LLM
    try:
        client = LLMClient()
        prompt = _build_prompt(projects)
        raw = client.generate(prompt, format_json=True)
        data = json.loads(raw) if isinstance(raw, str) else raw
        pill_list = data.get("pills", [])
    except Exception as e:
        logger.error(f"Work pills LLM call failed: {e}")
        return {"pills": {}, "cached": False, "error": str(e)}

    # Map clusters to colors and store in cache
    result = {}
    for entry in pill_list:
        pid = entry.get("project_id")
        items = entry.get("items", [])
        result[pid] = [
            {
                "label": item["label"],
                **COLOR_CLUSTERS.get(item.get("cluster", "build"), COLOR_CLUSTERS["build"]),
            }
            for item in items[:3]  # enforce max 3
        ]

    _pills_cache = result
    return {"pills": result, "cached": False}
