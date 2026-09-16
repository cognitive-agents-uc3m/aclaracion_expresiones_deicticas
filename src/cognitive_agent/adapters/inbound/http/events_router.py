from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ....adapters.outbound.events import event_to_dict
from ....domain.events import DomainEvent
from ....infrastructure.dependency_injection.container import Container
from .dependencies import get_container, session_id_of

router = APIRouter(prefix="/api/sessions", tags=["eventos"])

_HEARTBEAT_SECONDS = 20.0


@router.get("/{session_id}/events")
def retired_event_stream(session_id: str):
    raise HTTPException(
        status_code=410,
        detail="Utiliza la ruta actualizada del flujo de eventos.",
    )


@router.get("/{session_id}/events/stream")
async def stream_events(
    session_id: str, request: Request, container: Container = Depends(get_container)
):
    sid = session_id_of(session_id)
    queue: asyncio.Queue[DomainEvent] = asyncio.Queue(maxsize=256)
    loop = asyncio.get_running_loop()

    def on_event(event: DomainEvent) -> None:
        if event.session_id == sid:
            loop.call_soon_threadsafe(_offer, queue, event)

    unsubscribe = container.events.subscribe(on_event)

    async def generator() -> AsyncIterator[bytes]:
        try:
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield b": heartbeat\n\n"
                    continue
                payload = json.dumps(event_to_dict(event), ensure_ascii=False)
                yield f"event: {event.name}\ndata: {payload}\n\n".encode("utf-8")
        finally:
            unsubscribe()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/events/recent")
def recent_events(
    session_id: str, since: int = 0, container: Container = Depends(get_container)
):
    events = container.events.history(session_id_of(session_id), since=since)
    return {
        "since": since,
        "next": since + len(events),
        "events": [event_to_dict(event) for event in events],
    }


def _offer(queue: asyncio.Queue, event: DomainEvent) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
            queue.put_nowait(event)
        except (asyncio.QueueEmpty, asyncio.QueueFull):
            pass
