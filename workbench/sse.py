"""Server-Sent Events bus for real-time workbench updates."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from sse_starlette.sse import EventSourceResponse

from .auth import CurrentUser, decode_token


class EventType(str, Enum):
    JOB_CREATED = "job_created"
    JOB_STATUS_CHANGED = "job_status_changed"
    JOB_PROGRESS = "job_progress"
    ASSET_UPLOADED = "asset_uploaded"
    QUEUE_UPDATED = "queue_updated"
    USER_JOINED = "user_joined"


class EventBus:
    """In-process pub/sub for SSE. Each connected client gets an asyncio.Queue."""

    def __init__(self):
        self._subscribers: list[tuple[str, asyncio.Queue[dict]]] = []  # (role, queue)

    def publish(self, event_type: EventType, data: Any, visible_to: str = "all") -> None:
        """Push an event to all subscribers whose role matches visibility.

        `visible_to`:
          - "all" — everyone gets it
          - "admin" — only admins
          - a specific username — only that user
        """
        payload = {
            "type": event_type.value,
            "data": _json_safe(data),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Copy the list to avoid mutation during iteration
        for role, queue in list(self._subscribers):
            if visible_to == "all" or role == "admin" or role == visible_to:
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass  # drop event for slow clients

    async def subscribe(self, role: str) -> asyncio.Queue[dict]:
        """Register a new subscriber. Returns an unbounded queue."""
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        self._subscribers.append((role, queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        """Remove a subscriber."""
        self._subscribers = [(r, q) for r, q in self._subscribers if q is not queue]


# Singleton
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return value


async def _sse_auth(request: Request) -> CurrentUser:
    """Extract JWT from query param (EventSource can't set headers) or Authorization header."""
    # Try query param first
    token = request.query_params.get("authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]

    # Fall back to header
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        from .errors import PermissionDeniedError
        raise PermissionDeniedError("Missing authorization token")

    payload = decode_token(token)
    if payload is None or payload.get("typ") == "refresh":
        from .errors import PermissionDeniedError
        raise PermissionDeniedError("Invalid or expired token")

    return CurrentUser(
        id=str(payload["sub"]),
        username=payload["username"],
        role=payload["role"],
    )


async def sse_endpoint(request: Request, user: CurrentUser = Depends(_sse_auth)):
    """SSE endpoint: GET /api/events. Streams real-time workbench events to the client."""
    bus = get_event_bus()
    queue = await bus.subscribe(user.role)

    async def event_generator():
        # Send initial connected event
        yield {
            "event": "connected",
            "data": json.dumps({"username": user.username, "role": user.role}),
        }

        try:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": "message",
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield {
                        "event": "ping",
                        "data": "",
                    }
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(event_generator())
