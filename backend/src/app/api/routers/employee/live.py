"""The manager's live line: an inbox moved, so read it again.

A Server-Sent Events stream, boss-only. Each event names an inbox
(`requests` or `swaps`) and carries nothing else; the browser re-reads it
through the existing guarded route. So the stream adds *when* to the manager's
screen without adding a second *what* that would need its own scoping.

**It ends on its own after `lifetime` seconds.** `EventSource` reconnects by
itself, and the reconnect passes through `guards.boss()` again, so a team the
operator suspended (D28) or a cookie that expired stops listening within
minutes instead of holding an authorised stream open forever.
"""

import asyncio
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.common.events import TeamEvents

HEARTBEAT_SECONDS = 15.0
LIFETIME_SECONDS = 300.0
# How long the browser waits before reconnecting after the stream ends.
RETRY_MILLISECONDS = 2000

HEADERS = {
    # `no-transform` keeps the Next proxy's gzip from buffering the stream:
    # a compressed event arrives only once the buffer fills, i.e. not live.
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}


async def stream(
    events: TeamEvents, team_id: str, request: Optional[Request] = None,
    heartbeat: float = HEARTBEAT_SECONDS, lifetime: float = LIFETIME_SECONDS,
) -> AsyncIterator[str]:
    """SSE frames for one team until the client leaves or `lifetime` runs out.

    The heartbeat is a comment line: it keeps idle proxies from cutting the
    connection and lets a vanished client be noticed on the next write.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + lifetime
    with events.subscribe(team_id) as inbox:
        yield "retry: %d\n\n" % RETRY_MILLISECONDS
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            if request is not None and await request.is_disconnected():
                return
            try:
                kind = await asyncio.wait_for(
                    inbox.get(), timeout=min(heartbeat, remaining),
                )
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield "event: %s\ndata: {}\n\n" % kind


class LiveRoutes:
    def __init__(self, events: TeamEvents, boss):
        self._events = events
        self._boss = boss

    def register(self, router: APIRouter) -> None:
        events, boss = self._events, self._boss

        @router.get("/events")
        async def live(request: Request, session: dict = Depends(boss)):
            """Wake the manager's screen when an employee touches an inbox."""
            return StreamingResponse(
                stream(events, session["team_id"], request),
                media_type="text/event-stream",
                headers=HEADERS,
            )
