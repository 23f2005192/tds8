from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from collections import defaultdict, deque
from threading import Lock
import base64
import time

TOTAL_ORDERS = 58
RATE_LIMIT = 16
WINDOW = 10

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # or the exam origin if specified
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

lock = Lock()

catalog = [
    {
        "id": i,
        "user": f"user{i}",
        "amount": float(i * 10),
        "status": "catalog",
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

created_orders = {}
idempotency_map = {}
next_order_id = TOTAL_ORDERS + 1

rate_buckets = defaultdict(deque)


def encode_cursor(offset: int):
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str):
    return int(base64.urlsafe_b64decode(cursor.encode()).decode())


@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client = request.headers.get("X-Client-Id")

    if client:

        now = time.monotonic()

        with lock:

            bucket = rate_buckets[client]

            while bucket and now - bucket[0] >= WINDOW:
                bucket.popleft()

            if len(bucket) >= RATE_LIMIT:

                retry_after = max(
                    1,
                    int(WINDOW - (now - bucket[0])) + 1
                )

                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={
                        "Retry-After": str(retry_after)
                    },
                )

            bucket.append(now)

    return await call_next(request)


@app.post("/orders")
async def create_order(request: Request):

    global next_order_id

    body = await request.json()

    key = request.headers.get("Idempotency-Key")

    with lock:

        if key and key in idempotency_map:

            order_id = idempotency_map[key]

            return created_orders[order_id]

        order = {
            "id": next_order_id,
            "user": body.get("user", f"user{next_order_id}"),
            "amount": body.get("amount", 0),
            "status": "created",
        }

        created_orders[next_order_id] = order

        if key:
            idempotency_map[key] = next_order_id

        next_order_id += 1

    return JSONResponse(
        status_code=201,
        content=order,
    )


@app.get("/orders")
async def list_orders(limit: int = 10, cursor: str | None = None):

    if limit <= 0:
        limit = 10

    offset = decode_cursor(cursor) if cursor else 0

    items = catalog[offset:offset + limit]

    next_offset = offset + len(items)

    next_cursor = (
        encode_cursor(next_offset)
        if next_offset < TOTAL_ORDERS
        else None
    )

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@app.get("/")
async def root():
    return {"status": "running"}
