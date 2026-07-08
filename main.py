from fastapi import FastAPI
from pydantic import BaseModel
import re
from datetime import datetime

app = FastAPI()


class InvoiceRequest(BaseModel):
    text: str


class InvoiceResponse(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str


CURRENCIES = ["USD", "EUR", "GBP"]


@app.post("/extract", response_model=InvoiceResponse)
async def extract(req: InvoiceRequest):

    text = req.text.strip()

    if not text:
        return InvoiceResponse(
            vendor="",
            amount=0.0,
            currency="USD",
            date=""
        )

    # -------------------------
    # Currency
    # -------------------------

    currency = "USD"

    m = re.search(r"\b(USD|EUR|GBP)\b", text, re.IGNORECASE)

    if m:
        currency = m.group(1).upper()

    # -------------------------
    # Amount
    # -------------------------

    amount = 0.0

    patterns = [
        r"total\s+due[:\s]*[$€£]?\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"amount\s+due[:\s]*[$€£]?\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"balance\s+due[:\s]*[$€£]?\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"[$€£]\s*([0-9]+(?:\.[0-9]{1,2})?)",
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            amount = float(m.group(1))
            break

    # -------------------------
    # Date
    # -------------------------

    date = ""

    m = re.search(r"\b(20\d\d-\d\d-\d\d)\b", text)

    if m:
        date = m.group(1)
    else:

        m = re.search(
            r"(\d{1,2})/(\d{1,2})/(20\d\d)",
            text
        )

        if m:
            d, mo, y = m.groups()
            date = datetime(
                int(y),
                int(mo),
                int(d)
            ).strftime("%Y-%m-%d")

    # -------------------------
    # Vendor
    # -------------------------

    vendor = ""

    patterns = [
        r"Vendor[:\s]*(.+)",
        r"Supplier[:\s]*(.+)",
        r"From[:\s]*(.+)",
        r"Billed by[:\s]*(.+)",
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            vendor = m.group(1).split("\n")[0].strip()
            break

    if not vendor:
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        if lines:
            vendor = lines[0]

    return InvoiceResponse(
        vendor=vendor,
        amount=amount,
        currency=currency,
        date=date,
    )


@app.get("/")
async def root():
    return {"status": "running"}
