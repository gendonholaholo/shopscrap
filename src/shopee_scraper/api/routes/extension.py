"""WebSocket gateway for Chrome Extension connections."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shopee_scraper.extension.manager import get_extension_manager
from shopee_scraper.extension.protocol import (
    MessageType,
    RegisteredResponse,
    RegisterPayload,
    WebSocketMessage,
)
from shopee_scraper.utils.logging import get_logger


router = APIRouter(prefix="/extension", tags=["Extension"])
logger = get_logger(__name__)


@router.get("/status")
async def extension_status() -> dict:
    """List connected extensions and their status."""
    manager = get_extension_manager()
    connections = manager.get_connections()
    return {
        "connected": len(connections),
        "extensions": connections,
        "available": manager.has_available(),
    }


@router.websocket("/connect")
async def extension_connect(websocket: WebSocket) -> None:
    """WebSocket endpoint for Chrome Extension connections.

    Protocol:
    1. Extension connects
    2. Extension sends `register` message with extension_id
    3. Backend responds with `registered` confirmation
    4. Event loop: extension sends heartbeats, task results; backend sends tasks
    5. On disconnect: cleanup and fail pending tasks
    """
    await websocket.accept()
    extension_id: str | None = None
    manager = get_extension_manager()

    try:
        # Wait for registration message
        raw = await websocket.receive_text()
        message = WebSocketMessage.model_validate_json(raw)

        if message.type != MessageType.REGISTER:
            await websocket.send_text(
                json.dumps({"error": "Expected register message"})
            )
            await websocket.close(code=1008)
            return

        # Validate and register
        payload = RegisterPayload(**message.payload)
        extension_id = payload.extension_id
        manager.register(websocket, payload)

        # Send registered confirmation
        response = RegisteredResponse()
        confirm = WebSocketMessage.create(
            MessageType.REGISTERED,
            **response.model_dump(),
        )
        await websocket.send_text(confirm.to_json_str())

        logger.info("Extension connected and registered", extension_id=extension_id)

        # Main event loop
        while True:
            raw = await websocket.receive_text()
            try:
                message = WebSocketMessage.model_validate_json(raw)
                await manager.handle_message(extension_id, message)
            except Exception as e:
                logger.warning(
                    "Invalid message from extension",
                    extension_id=extension_id,
                    error=str(e),
                )

    except WebSocketDisconnect:
        logger.info("Extension disconnected", extension_id=extension_id)
    except Exception as e:
        logger.error("Extension WebSocket error", error=str(e))
    finally:
        if extension_id:
            await manager.unregister(extension_id)
