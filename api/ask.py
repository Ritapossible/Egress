"""Vercel serverless entry point for the desk.

The LLM key lives here and only here. It cannot go in the browser, which is the
entire reason this endpoint exists rather than a client-side call.

Three things this layer guarantees, none of which the desk can guarantee alone:

- **The response is valid JSON or it is an error.** `json.dumps` will happily
  emit a bare `NaN`, which every conforming parser rejects; `allow_nan=False`
  turns that into a failure here rather than a parse error in someone's browser.
- **No exception reaches the platform.** A traceback becomes an HTML 500 page,
  and an HTML page is not something the client can read an error out of.
- **One caller cannot spend the whole key.** The reader is metered and the
  venue is not ours to hammer.
"""
from __future__ import annotations

import json
import sys
import time
from collections import deque
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import desk, llm

MAX_BODY = 4096
MAX_QUESTION = 600

# Per-instance, best effort. Serverless gives no shared state, so this bounds a
# single warm instance rather than the deployment - enough to stop one tab or
# one loop from draining the key, and deliberately not presented as more.
RATE_WINDOW_S = 60.0
RATE_LIMIT = 12
_recent: deque[float] = deque()


def _over_rate_limit() -> bool:
    now = time.monotonic()
    while _recent and now - _recent[0] > RATE_WINDOW_S:
        _recent.popleft()
    if len(_recent) >= RATE_LIMIT:
        return True
    _recent.append(now)
    return False


# Vercel's Python runtime requires this exact lowercase class name.
class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        try:
            body = json.dumps(payload, allow_nan=False).encode()
        except ValueError:
            # A non-finite number got this far. Say so rather than shipping a
            # body the client cannot parse.
            status, body = 500, json.dumps(
                {"error": "the desk produced an unrepresentable number"}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        """No request logging: questions are user content, not telemetry."""

    def do_POST(self) -> None:          # http.server's own naming
        try:
            declared = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "bad Content-Length"})
            return
        if declared > MAX_BODY:
            self._send(413, {"error": f"question body over {MAX_BODY} bytes"})
            return
        try:
            question = json.loads(self.rfile.read(declared) or b"{}").get("q", "")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": 'send JSON: {"q": "your question"}'})
            return
        if not isinstance(question, str) or not question.strip():
            self._send(400, {"error": "ask something"})
            return
        if not llm.configured():
            self._send(503, {"error": "the desk is not configured: QWEN_API_KEY "
                                      "is not set on this deployment"})
            return
        if _over_rate_limit():
            self._send(429, {"error": f"too many questions - more than "
                                      f"{RATE_LIMIT} in {RATE_WINDOW_S:.0f}s. "
                                      f"Wait a moment and ask again."})
            return
        try:
            answer = desk.answer(question[:MAX_QUESTION])
        except Exception as exc:        # nothing may reach Vercel as a traceback
            self._send(502, {"error": f"the desk failed while answering: "
                                      f"{type(exc).__name__}"})
            return
        self._send(200, answer)

    def do_GET(self) -> None:
        self._send(200, {"ok": True, "reader_configured": llm.configured(),
                         "usage": 'POST {"q": "what does leaving 40k of TSLA cost?"}'})
