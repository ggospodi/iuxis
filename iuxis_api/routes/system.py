"""iuxis_api/routes/system.py — System health + stats endpoints."""

from fastapi import APIRouter, Depends
from iuxis_api.deps import get_db

router = APIRouter()


@router.get("/health")
def health():
    from iuxis.llm_client import LLMClient
    client = LLMClient()
    llm_status = client.health_check()
    return {
        "status": "ok",
        "llm": llm_status,
        "primary_model":  llm_status.get("primary_model",  "qwen3.5-35b-a3b"),
        "fallback_model": llm_status.get("fallback_model", "deepseek-r1:32b"),
    }


@router.get("/stats")
def stats(conn=Depends(get_db)):
    cur = conn.cursor()
    def count(table, where="1=1"):
        try:
            return cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]
        except Exception:
            return 0

    return {
        "projects": {
            "total":  count("projects"),
            "active": count("projects", "status='active'"),
        },
        "tasks": {
            "total":       count("tasks"),
            "todo":        count("tasks", "status='todo'"),
            "in_progress": count("tasks", "status='in_progress'"),
            "done":        count("tasks", "status='done'"),
        },
        "knowledge": {
            "total": count("user_knowledge"),
        },
        "insights": count("insights"),
        "chat_messages": count("chat_history"),
    }

@router.get("/open-inbox")
def open_inbox():
    """Open the inbox folder in the system file explorer."""
    import os
    import subprocess
    import platform

    inbox_path = os.path.expanduser("~/iuxis-inbox")
    os.makedirs(inbox_path, exist_ok=True)

    try:
        system = platform.system()
        if system == "Darwin":  # macOS
            subprocess.run(["open", inbox_path])
        elif system == "Windows":
            subprocess.run(["explorer", inbox_path])
        else:  # Linux
            subprocess.run(["xdg-open", inbox_path])
        return {"status": "ok", "path": inbox_path}
    except Exception as e:
        return {"status": "error", "error": str(e)}
