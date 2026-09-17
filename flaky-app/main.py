# This app is intentionally designed to fail in predictable ways.
# It acts as the "service under observation" so the monitoring system can
# detect unhealthy behavior and test automatic recovery.

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI


# These settings control how aggressively the app simulates a memory leak.
# A small value keeps local testing gentle, while a larger value makes
# the resource use grow faster for demos.
LEAK_CHUNK_BYTES = int(os.getenv("LEAK_CHUNK_MB", "1")) * 1024 * 1024
LEAK_INTERVAL_SECONDS = float(os.getenv("LEAK_INTERVAL_SECONDS", "0.25"))

# This list keeps references to every leaked chunk so the memory remains
# allocated and cannot be freed by Python's garbage collector.
_leaked_chunks: list[bytearray] = []

# The background leak task is tracked so it can be stopped cleanly when the
# app shuts down.
_leak_task: asyncio.Task[None] | None = None


async def allocate_memory_forever() -> None:
    """Continuously allocate memory to simulate a gradual resource leak."""
    while True:
        chunk = bytearray(LEAK_CHUNK_BYTES)

        # Touch each memory page so RSS reflects the allocation immediately.
        for page in range(0, len(chunk), 4096):
            chunk[page] = 1

        _leaked_chunks.append(chunk)
        await asyncio.sleep(LEAK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Clean up background tasks when the FastAPI server stops."""
    yield
    if _leak_task is not None:
        _leak_task.cancel()


# This FastAPI app exposes health and failure endpoints for demos and tests.
app = FastAPI(title="flaky-app", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple health endpoint used by monitor checks."""
    return {"status": "ok"}


@app.post("/leak/start", status_code=202)
async def start_leak() -> dict[str, str]:
    """Start a background memory leak so the app slows down over time."""
    global _leak_task

    if _leak_task is None or _leak_task.done():
        _leak_task = asyncio.create_task(allocate_memory_forever())
        return {"status": "leak started"}

    return {"status": "leak already running"}


@app.post("/chaos/crash", status_code=202)
async def crash() -> None:
    """Kill the process immediately to simulate a hard service failure."""
    os._exit(1)