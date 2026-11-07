"""Tiny orders API used as the diagnosis target. Deterministic and small."""

from __future__ import annotations

import json
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError

CRASH_ON_START = os.environ.get("CRASH_ON_START", "0") == "1"
if CRASH_ON_START:
    raise RuntimeError("invalid configuration: CRASH_ON_START=1")

# Invalid JSON in ORDERS_CONFIG is an intentional crash-loop fault.
json.loads(os.environ.get("ORDERS_CONFIG", "{}"))

allocate_mb = int(os.environ.get("ALLOCATE_MB", "0") or "0")
_hold: list[bytes] = []
if allocate_mb > 0:
    _hold.append(b"x" * (allocate_mb * 1024 * 1024))

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
QUEUE_KEY = "orders"
RESULT_KEY = "orders:done"

app = FastAPI(title="orders")


def redis_client() -> Redis:
    return Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    try:
        redis_client().ping()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}") from exc
    return {"status": "ready"}


@app.get("/queue")
def queue_depth() -> dict[str, int]:
    try:
        length = int(redis_client().llen(QUEUE_KEY))
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"length": length}


@app.post("/orders")
def create_order() -> JSONResponse:
    client = redis_client()
    token = f"order-{time.time_ns()}"
    try:
        client.lpush(QUEUE_KEY, token)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            done = client.lrange(RESULT_KEY, 0, 20)
            if any(item.decode() == token for item in done):
                return JSONResponse({"status": "done", "id": token})
            time.sleep(0.1)
        length = int(client.llen(QUEUE_KEY))
        return JSONResponse(
            {
                "status": "timeout",
                "id": token,
                "queue_length": length,
                "detail": "order queued but not processed",
            },
            status_code=504,
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
