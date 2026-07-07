import base64
import json
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import FastAPI, Request, HTTPException, Response, Header, Depends
from fastapi.middleware.cors import CORSMiddleware

# ---- Assigned config ----
TOTAL_ORDERS = 58          # T
RATE_LIMIT = 16            # R requests
RATE_WINDOW_SECONDS = 10   # per 10s

app = FastAPI()

# CORSMiddleware must be the only/outermost middleware so that EVERY
# response - including 429s and error responses - gets CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- In-memory state ----
lock = Lock()

catalog = [
    {"id": i, "user": f"user{i}", "amount": round(10 + (i * 7 % 90) + 0.5, 2), "status": "catalog"}
    for i in range(1, TOTAL_ORDERS + 1)
]

created_orders = {}          # order_id -> order dict
idempotency_map = {}         # idempotency_key -> order_id
next_created_id = TOTAL_ORDERS + 1

rate_buckets = defaultdict(deque)  # client_id -> deque of request timestamps


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


def enforce_rate_limit(x_client_id: str | None = Header(default=None)):
    """FastAPI dependency (not middleware) so HTTPException still flows
    through CORSMiddleware and gets Access-Control-Allow-Origin set."""
    if x_client_id is None:
        return

    now = time.monotonic()
    with lock:
        bucket = rate_buckets[x_client_id]
        while bucket and now - bucket[0] > RATE_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = max(0, RATE_WINDOW_SECONDS - (now - bucket[0]))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        bucket.append(now)


@app.post("/orders", dependencies=[Depends(enforce_rate_limit)])
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
                return created_orders[existing_id]

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


@app.get("/orders", dependencies=[Depends(enforce_rate_limit)])
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
