"""Background worker that drains the orders Redis list."""

from __future__ import annotations

import os
import time

from redis import Redis

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
QUEUE_KEY = "orders"
RESULT_KEY = "orders:done"


def main() -> None:
    client = Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=2.0)
    if os.environ.get("WORKER_STUCK") == "1":
        print("WORKER_STUCK=1 enabled; worker is not consuming the queue", flush=True)
        while True:
            time.sleep(60)

    print(f"worker connecting to {REDIS_HOST}:{REDIS_PORT}", flush=True)
    while True:
        item = client.blpop(QUEUE_KEY, timeout=5)
        if not item:
            continue
        _queue, payload = item
        token = payload.decode()
        print(f"processing {token}", flush=True)
        client.lpush(RESULT_KEY, token)
        client.ltrim(RESULT_KEY, 0, 100)


if __name__ == "__main__":
    main()
