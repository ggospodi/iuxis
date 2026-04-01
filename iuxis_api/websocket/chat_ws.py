"""WebSocket for streaming chat responses."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()

@router.websocket("/ws/chat/{channel_id}")
async def chat_websocket(websocket: WebSocket, channel_id: int):
    """
    Bidirectional chat via WebSocket.
    Client sends: {"message": "generate briefing"}
    Server sends: {"type": "response", "content": "full response text"}
    Server sends: {"type": "error", "content": "error message"}
    """
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            user_message = payload.get("message", "")

            if not user_message:
                await websocket.send_json({"type": "error", "content": "Empty message"})
                continue

            try:
                from iuxis.db import get_connection
                from iuxis.chat_handler import ChatHandler

                conn = get_connection()
                handler = ChatHandler(conn)

                # Send "thinking" indicator
                await websocket.send_json({"type": "thinking", "content": "Processing..."})

                # Get response (returns dict with response, save_signal, etc.)
                result = handler.handle_message(user_message)

                await websocket.send_json({
                    "type": "response",
                    "content": result.get("response", ""),
                    "save_signal": result.get("save_signal"),
                    "channel_id": channel_id
                })
            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)})

    except WebSocketDisconnect:
        pass
