from fastapi import FastAPI
from pydantic import BaseModel
import re

app = FastAPI()


class InvoiceRequest(BaseModel):
    text: str


class InvoiceResponse(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str


def extract_vendor(text: str) -> str:

    patterns = [
        r"Vendor\s*:\s*(.+)",
        r"Supplier\s*:\s*(.+)",
        r"From\s*:\s*(.+)",
        r"Billed\s+By\s*:\s*(.+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).split("\n")[0].strip()

    company = re.search(
        r"([A-Za-z0-9&,\- ]+(?:Ltd\.?|Limited|LLC|Inc\.?|Corporation|Company|Industries))",
        text,
        re.IGNORECASE,
    )

    if company:
        return company.group(1).strip()

    lines = [x.strip() for x in text.splitlines() if x.strip()]

    if lines:
        return lines[0]

    return ""


def extract_currency(text: str) -> str:

    m = re.search(r"\b(USD|EUR|GBP)\b", text, re.IGNORECASE)

    if m:
        return m.group(1).upper()

    symbols = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
    }

    for symbol, code in symbols.items():
        if symbol in text:
            return code

    return "USD"


def extract_amount(text: str) -> float:

    patterns = [

        r"Total\s*Due\s*[:\-]?\s*(?:USD|EUR|GBP)?\s*[$€£]?\s*([0-9]+(?:\.[0-9]{2})?)",

        r"Amount\s*Due\s*[:\-]?\s*(?:USD|EUR|GBP)?\s*[$€£]?\s*([0-9]+(?:\.[0-9]{2})?)",

        r"Balance\s*Due\s*[:\-]?\s*(?:USD|EUR|GBP)?\s*[$€£]?\s*([0-9]+(?:\.[0-9]{2})?)",

        r"Payment\s*[:\-]?\s*(?:USD|EUR|GBP)?\s*[$€£]?\s*([0-9]+(?:\.[0-9]{2})?)",

        r"(?:USD|EUR|GBP)\s*([0-9]+(?:\.[0-9]{2})?)",

        r"([0-9]+(?:\.[0-9]{2})?)\s*(?:USD|EUR|GBP)",

        r"[$€£]\s*([0-9]+(?:\.[0-9]{2})?)",
    ]

    for pattern in patterns:

        m = re.search(pattern, text, re.IGNORECASE)

        if m:
            return float(m.group(1))

    numbers = re.findall(r"\d+\.\d{2}", text)

    if numbers:
        return max(float(x) for x in numbers)

    integers = re.findall(r"\b\d+\b", text)

    values = []

    for value in integers:
        try:
            n = int(value)
            if 50 <= n <= 100000:
                values.append(n)
        except Exception:
            pass

    if values:
        return float(max(values))

    return 0.0


def extract_date(text: str) -> str:

    m = re.search(r"\b20\d\d-\d\d-\d\d\b", text)

    if m:
        return m.group(0)

    return ""


@app.post("/extract", response_model=InvoiceResponse)
async def extract(req: InvoiceRequest):

    text = req.text.strip()

    return InvoiceResponse(
        vendor=extract_vendor(text),
        amount=extract_amount(text),
        currency=extract_currency(text),
        date=extract_date(text),
    )


@app.get("/")
async def root():
    return {"status": "running"}
