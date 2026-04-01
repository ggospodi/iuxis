"""WebSocket for live dashboard updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json

router = APIRouter()

# Simple in-memory connection manager
class DashboardManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = DashboardManager()

@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """
    Push updates when DB changes.
    Sends: {"type": "update", "entity": "task|insight|briefing|knowledge", "data": {...}}
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for ping
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
