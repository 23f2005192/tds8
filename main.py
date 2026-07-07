import base64
import json
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

# ---- Assigned config ----
TOTAL_ORDERS = 58          # T
RATE_LIMIT = 16            # R requests
RATE_WINDOW_SECONDS = 10   # per 10s

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- In-memory state ----
lock = Lock()

# Fixed catalog of orders 1..T, used for pagination scans.
catalog = [
    {"id": i, "user": f"user{i}", "amount": round(10 + (i * 7 % 90) + 0.5, 2), "status": "catalog"}
    for i in range(1, TOTAL_ORDERS + 1)
]

# Orders created via POST /orders (idempotent creation), stored separately.
created_orders = {}          # order_id -> order dict
idempotency_map = {}         # idempotency_key -> order_id
next_created_id = TOTAL_ORDERS + 1

# Rate limiting: client_id -> deque of request timestamps (monotonic)
rate_buckets = defaultdict(deque)


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id")
    if client_id is None:
        return await call_next(request)

    now = time.monotonic()
    with lock:
        bucket = rate_buckets[client_id]
        while bucket and now - bucket[0] > RATE_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = max(0, RATE_WINDOW_SECONDS - (now - bucket[0]))
            headers = {"Retry-After": str(int(retry_after) + 1)}
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers=headers,
            )

        bucket.append(now)

    return await call_next(request)


@app.post("/orders")
async def create_order(request: Request):
    global next_created_id

    idempotency_key = request.headers.get("Idempotency-Key")
    try:
        body = await request.json()
    except Exception:
        body = {}

    if idempotency_key:
        with lock:
            existing_id = idempotency_map.get(idempotency_key)
            if existing_id is not None:
                order = created_orders[existing_id]
                return order

    with lock:
        order_id = next_created_id
        next_created_id += 1
        order = {
            "id": order_id,
            "user": body.get("user", f"user{order_id}"),
            "amount": body.get("amount", 0),
            "status": "created",
        }
        created_orders[order_id] = order
        if idempotency_key:
            idempotency_map[idempotency_key] = order_id

    return Response(
        content=json.dumps(order),
        status_code=201,
        media_type="application/json",
    )


@app.get("/orders")
async def list_orders(limit: int = 10, cursor: str | None = None):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")

    offset = decode_cursor(cursor) if cursor else 0
    if offset < 0 or offset > TOTAL_ORDERS:
        raise HTTPException(status_code=400, detail="Invalid cursor")

    items = catalog[offset: offset + limit]
    new_offset = offset + len(items)
    next_cursor = encode_cursor(new_offset) if new_offset < TOTAL_ORDERS else None

    return {
        "items": items,
        "orders": items,
        "next_cursor": next_cursor,
        "next": next_cursor,
    }