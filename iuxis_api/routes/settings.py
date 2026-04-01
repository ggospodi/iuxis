"""Settings endpoints for reading and writing configuration."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from iuxis_api.deps import get_db

router = APIRouter()


# Default values for settings
DEFAULTS = {
    "llm_backend": "ollama",
    "llm_model": "qwen2.5:32b",
    "llm_url": "http://127.0.0.1:11434",
    "lmstudio_url": "http://127.0.0.1:1234",
    "ollama_url": "http://127.0.0.1:11434",
    "briefing_time": "08:00",
    "refresh_interval": "300",
    "auto_refresh": "true",
    "max_projects": "12",
    "github_enabled": "false",
    "github_org": "",
    "backfill_days": "60",
}


class SettingsUpdate(BaseModel):
    """Request model for updating settings."""
    settings: dict[str, Any]


@router.get("/settings")
def get_settings(db=Depends(get_db)):
    """Get all settings from config table.

    Returns flat JSON with all configuration keys.
    Missing keys return sensible defaults.
    """
    # Fetch all existing settings
    rows = db.execute("SELECT key, value FROM config").fetchall()

    # Build settings dict from DB
    settings = {row["key"]: row["value"] for row in rows}

    # Merge with defaults for missing keys
    result = {**DEFAULTS, **settings}

    return result


@router.post("/settings")
def update_settings(request: SettingsUpdate, db=Depends(get_db)):
    """Update multiple settings.

    Accepts a body like: {"settings": {"llm_model": "qwen2.5:32b", "briefing_time": "06:05"}}
    Upserts each key into the config table.
    """
    if not request.settings:
        raise HTTPException(status_code=400, detail="No settings provided")

    # Upsert each setting
    for key, value in request.settings.items():
        # Convert value to string for storage
        str_value = str(value) if value is not None else ""

        db.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, str_value)
        )

    db.commit()

    return {"saved": True, "count": len(request.settings)}
