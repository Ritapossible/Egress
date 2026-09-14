"""The reader: plain English in, a structured request out.

The model does translation, never judgement. It turns "I hold 40k of Tesla, what
does getting out cost" into {symbol, notional_usdt} and stops there. Every number
the desk returns is computed afterwards by `exitcost` against the live book, so a
wrong answer is a visibly wrong SPEC rather than an invented figure.

That division is deliberate. An LLM asked to estimate a cost will produce one, and
it will look reasonable, and it will be fiction.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

BASE_URL = os.environ.get("QWEN_BASE_URL", "https://hackathon.bitgetops.com/v1")
MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-max")
TIMEOUT_S = 25

SYSTEM = (
    "You translate a trader's plain-English question about leaving a position "
    "into JSON. Reply with ONLY a JSON object, no prose, no code fence. Keys: "
    '"ticker" (the US stock ticker in capitals, e.g. TSLA, NVDA, AAPL - never a '
    'token name, never with an R prefix), "notional_usdt" (number, the position '
    "size in USDT; use 25000 if the question does not give one), and "
    '"confident" (true only if the ticker is stated or unmistakable). If you '
    'cannot identify a ticker set "ticker" to null.'
)


class ReaderUnavailable(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def configured() -> bool:
    return bool(os.environ.get("QWEN_API_KEY") or os.environ.get("BITGET_QWEN_KEY"))


def _key() -> str | None:
    return os.environ.get("QWEN_API_KEY") or os.environ.get("BITGET_QWEN_KEY")


def _extract(text: str) -> dict:
    """Pull the JSON object out, tolerating a fence or stray prose around it."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ReaderUnavailable("the reader returned no JSON object")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ReaderUnavailable(f"unparseable JSON from the reader: {exc}") from None
    if not isinstance(parsed, dict):
        raise ReaderUnavailable("the reader returned JSON that was not an object")
    return parsed


def compile_question(question: str) -> dict:
    """{ticker, notional_usdt, confident} - or a typed failure."""
    key = _key()
    if not key:
        raise ReaderUnavailable("QWEN_API_KEY is not set")
    if not question.strip():
        raise ReaderUnavailable("empty question")

    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": question[:600]}],
        "temperature": 0,
        "max_tokens": 160,
    }).encode()
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise ReaderUnavailable(f"reader http {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ReaderUnavailable(f"reader unreachable: {exc.reason}") from None
    except TimeoutError:
        raise ReaderUnavailable(f"reader timeout after {TIMEOUT_S}s") from None
    except json.JSONDecodeError as exc:
        raise ReaderUnavailable(f"malformed reader response: {exc}") from None

    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ReaderUnavailable("reader response had no message content") from None

    spec = _extract(text)
    ticker = spec.get("ticker")
    ticker = str(ticker).strip().upper() if ticker else None
    if ticker and not re.fullmatch(r"[A-Z.]{1,8}", ticker):
        ticker = None
    try:
        notional = float(spec.get("notional_usdt") or 25_000)
    except (TypeError, ValueError):
        notional = 25_000.0
    return {"ticker": ticker, "notional_usdt": max(1.0, min(notional, 50_000_000.0)),
            "confident": bool(spec.get("confident")), "model": MODEL}
