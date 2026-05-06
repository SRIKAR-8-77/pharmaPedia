"""
WebSocket server for real-time HIGH signal alerts.
Redis pub/sub → FastAPI WebSocket → React client.
Phase 1: connection management wired.
Phase 3: Redis pub/sub integration for live HIGH signal push.
"""
import json
import asyncio
import logging
from typing import Dict, Set
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# project_id → set of active websocket connections
_connections: Dict[str, Set[WebSocket]] = {}


class ConnectionManager:
    def connect(self, project_id: str, ws: WebSocket):
        _connections.setdefault(project_id, set()).add(ws)

    def disconnect(self, project_id: str, ws: WebSocket):
        if project_id in _connections:
            _connections[project_id].discard(ws)

    async def broadcast(self, project_id: str, message: dict):
        conns = _connections.get(project_id, set()).copy()
        dead = set()
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            _connections[project_id].discard(ws)


manager = ConnectionManager()


async def _redis_listener(project_id: str):
    """Subscribe to project-specific Redis channel and forward to WS clients."""
    r = aioredis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    channel = f"project:{project_id}:signals"
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(project_id, data)
                except Exception as e:
                    logger.error(f"WS broadcast error: {e}")
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()


@router.websocket("/projects/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    await websocket.accept()
    manager.connect(project_id, websocket)

    # Start Redis listener for this project if no connections existed before
    listener_task = None
    if len(_connections.get(project_id, set())) == 1:
        listener_task = asyncio.create_task(_redis_listener(project_id))

    try:
        while True:
            # Keep connection alive — client sends ping every 30s
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
        if listener_task and not _connections.get(project_id):
            listener_task.cancel()
