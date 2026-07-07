from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict

API_KEY = "ak_fnby2xsg52u57ilx9mc270c5"
EMAIL = "23f2005192@ds.study.iitm.ac.in"  # <-- replace with the email tied to your account

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/analytics")
async def analytics(request: Request):
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    events = body.get("events", [])

    total_events = len(events)
    unique_users = len({e["user"] for e in events})

    revenue = 0.0
    per_user_positive = defaultdict(float)

    for e in events:
        amount = e.get("amount", 0)
        if amount > 0:
            revenue += amount
            per_user_positive[e["user"]] += amount

    top_user = max(per_user_positive, key=per_user_positive.get) if per_user_positive else None

    return {
        "email": EMAIL,
        "total_events": total_events,
        "unique_users": unique_users,
        "revenue": round(revenue, 2),
        "top_user": top_user,
    }