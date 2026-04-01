"""Chat endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from iuxis_api.deps import get_db

router = APIRouter()


class SaveKnowledgeRequest(BaseModel):
    content: str
    category: str = "fact"
    project_id: Optional[int] = None
    source: str = "chat"


@router.post("")
def send_message(body: dict, db=Depends(get_db)):
    """Send a chat message and get response."""
    from iuxis.chat_handler import ChatHandler
    handler = ChatHandler(db)
    user_message = body.get("message", "")
    channel_id = body.get("channel_id", 1)
    project_id = body.get("project_id")

    result = handler.handle_message(user_message, project_id=project_id)
    return {
        "response": result.get("response", ""),
        "save_signal": result.get("save_signal"),
        "saved_entry": result.get("saved_entry"),
        "command": result.get("command"),
        "channel_id": channel_id,
    }


@router.post("/save-knowledge")
def save_knowledge_from_chat(request: SaveKnowledgeRequest, db=Depends(get_db)):
    """
    Called when user clicks 'Save' in the ChatSaveAffordance component.
    Saves the provided content as a knowledge entry.
    """
    from iuxis.knowledge_manager import add_knowledge
    from iuxis.chat_handler import compute_importance

    importance = compute_importance(
        category=request.category,
        content=request.content,
        source="chat",
        confidence="high",
    )

    entry_id = add_knowledge(
        category=request.category,
        content=request.content,
        source="chat",
        confidence="high",
        project_id=request.project_id,
        status="approved",
    )

    return {
        "success": True,
        "entry_id": entry_id,
        "importance": importance,
        "category": request.category,
    }

@router.get("/history/{channel_id}")
def chat_history(channel_id: int, limit: int = 50, db=Depends(get_db)):
    """Get chat history for a channel."""
    rows = db.execute("""
        SELECT id, role, content, created_at
        FROM chat_history
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    messages = [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
                for r in reversed(rows)]
    return {"messages": messages, "channel_id": channel_id}

@router.get("/channels")
def list_channels(db=Depends(get_db)):
    """List chat channels."""
    rows = db.execute("SELECT * FROM chat_channels ORDER BY id").fetchall()
    columns = [desc[0] for desc in db.execute("SELECT * FROM chat_channels LIMIT 0").description]
    channels = [dict(zip(columns, row)) for row in rows]
    return {"channels": channels}
