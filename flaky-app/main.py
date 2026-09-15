import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI


LEAK_CHUNK_BYTES = int(os.getenv("LEAK_CHUNK_MB", "1")) * 1024 * 1024
LEAK_INTERVAL_SECONDS = float(os.getenv("LEAK_INTERVAL_SECONDS", "0.25"))

_leaked_chunks: list[bytearray] = []
_leak_task: asyncio.Task[None] | None = None


async def allocate_memory_forever() -> None:
    """Keep allocations reachable so Python cannot reclaim them."""
    while True:
        chunk = bytearray(LEAK_CHUNK_BYTES)

        # Touch each memory page so RSS reflects the allocation immediately.
        for page in range(0, len(chunk), 4096):
            chunk[page] = 1

        _leaked_chunks.append(chunk)
        await asyncio.sleep(LEAK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    if _leak_task is not None:
        _leak_task.cancel()


app = FastAPI(title="flaky-app", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/leak/start", status_code=202)
async def start_leak() -> dict[str, str]:
    global _leak_task

    if _leak_task is None or _leak_task.done():
        _leak_task = asyncio.create_task(allocate_memory_forever())
        return {"status": "leak started"}

    return {"status": "leak already running"}


@app.post("/chaos/crash", status_code=202)
async def crash() -> None:
    os._exit(1)