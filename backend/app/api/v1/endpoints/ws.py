"""
WebSocket endpoint — Phase 4
Streams review pipeline status (queued → reviewing → completed/failed) to the
dashboard as review_worker processes PRs, instead of the client polling.
"""
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
import structlog

from app.core.security import decode_token
from app.services.ws_manager import ws_manager

log = structlog.get_logger()
router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/reviews")
async def review_events(websocket: WebSocket, token: str = Query(...)):
    """
    Real-time channel for review status updates for the current user.
    Auth is via a `token` query param — browsers cannot attach an
    Authorization header to the WebSocket handshake.
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "access" or not payload.get("sub"):
            raise ValueError("invalid token payload")
        user_id = int(payload["sub"])
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(user_id, websocket)
    log.info("WebSocket connected", user_id=user_id)
    try:
        while True:
            # Clients don't need to send anything; this just keeps the
            # handler alive to detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(user_id, websocket)
        log.info("WebSocket disconnected", user_id=user_id)
