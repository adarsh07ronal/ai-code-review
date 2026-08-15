"""
WebSocket connection manager — Phase 4

Review updates are produced by review_worker, which may run on any backend
replica behind the load balancer. Rather than holding sockets in a plain
dict (which only works for a single process), connections are tracked
locally per-instance and events are fanned out through a shared Redis
channel, so a client stays in sync no matter which replica processed the
review that triggered the update.
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, Optional, Set

import structlog
from fastapi import WebSocket

from app.db.redis import get_redis_client

log = structlog.get_logger()

CHANNEL = "ws:review-events"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._listener_task: Optional[asyncio.Task] = None

    # ── Local connection tracking ────────────────────────────────────────────

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        conns = self._connections.get(user_id)
        if not conns:
            return
        conns.discard(ws)
        if not conns:
            self._connections.pop(user_id, None)

    async def _dispatch_local(self, user_id: int, event_type: str, payload: dict) -> None:
        conns = self._connections.get(user_id)
        if not conns:
            return
        message = {"type": event_type, "payload": payload}
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.discard(ws)

    # ── Cross-replica fan-out via Redis pub/sub ──────────────────────────────

    async def publish(self, user_id: int, event_type: str, payload: dict) -> None:
        """Publish an event for `user_id`; every replica's listener will relay
        it to any locally-connected socket for that user."""
        redis = await get_redis_client()
        message = json.dumps({"user_id": user_id, "type": event_type, "payload": payload})
        await redis.publish(CHANNEL, message)

    async def start_listener(self) -> None:
        redis = await get_redis_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        self._listener_task = asyncio.create_task(self._listen(pubsub))
        log.info("WebSocket event listener started", channel=CHANNEL)

    async def stop_listener(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None

    async def _listen(self, pubsub) -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await self._dispatch_local(data["user_id"], data["type"], data["payload"])
                except Exception as exc:
                    log.warning("Failed to dispatch ws event", error=str(exc))
        except asyncio.CancelledError:
            pass


ws_manager = ConnectionManager()
