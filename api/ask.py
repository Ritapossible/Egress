"""Vercel serverless entry point for the desk.

The LLM key lives here and only here. It cannot go in the browser, which is the
entire reason this endpoint exists rather than a client-side call.
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import desk, llm

MAX_BODY = 4096


# Vercel's Python runtime requires this exact lowercase class name.
class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:          # http.server's own naming
        try:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
            question = json.loads(self.rfile.read(length) or b"{}").get("q", "")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "send JSON: {\"q\": \"your question\"}"})
            return
        if not str(question).strip():
            self._send(400, {"error": "ask something"})
            return
        if not llm.configured():
            self._send(503, {"error": "the desk is not configured: QWEN_API_KEY "
                                      "is not set on this deployment"})
            return
        self._send(200, desk.answer(str(question)))

    def do_GET(self) -> None:
        self._send(200, {"ok": True, "reader_configured": llm.configured(),
                         "usage": 'POST {"q": "what does leaving 40k of TSLA cost?"}'})
