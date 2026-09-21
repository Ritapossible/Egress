"""The Bitget MCP Skill, used for one thing: where the actual share last traded.

Egress walks the rToken's order book. That tells you what leaving costs on this
venue; it cannot tell you what the thing is worth, because the market that
prices it is shut for most of the week - which is the whole premise of this
project.

`equity_price_quote` is Bitget's own Skill for the listed US share. Asking it
turns "exiting costs 14 bp" into "exiting costs 14 bp on a position marked
146 bp away from where the share last printed, 57 hours ago". That second
sentence is the product.

Transport notes, each of which cost a round trip to learn on the Ballast build
this is ported from:

- Cloudflare rejects urllib's default User-Agent with `browser_signature_banned`.
- The handshake needs `notifications/initialized` (202) between `initialize`
  and the first `tools/call`.
- Sessions do not survive a second call, so each call re-handshakes.
- The stream may open with an SSE comment (`: ping`) before any `data:` line.
- The tool answers HTTP 200 and wraps the upstream's own status in the body, so
  a 503 arrives looking like a success and has to be unwrapped.

No dependencies, like everything else here.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

# Two of the organiser's MCP services, same transport, different catalogues.
# DATA is bitget-mcp-server (US stock quotes, fundamentals, earnings calendar).
# SIGNAL is bitget-signal (macro, sentiment, technical, news - no key needed).
ENDPOINT = "https://agent.bitget.com/mcp"
PROTOCOL = "2024-11-05"
# The desk answers a person waiting on a page. Ballast could afford 30s and
# three retries because a nightly job has all night; here the same budget is
# 90 seconds of someone staring at a spinner. The reference is additive, so it
# gets one attempt and a short fuse - if the Skill is slow the answer ships
# without it, saying so, which is what every other failure here does.
TIMEOUT = 6
RETRIES = 1

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class McpUnavailable(RuntimeError):
    """The service could not be reached, or answered something unusable.

    Never swallowed into an empty result: a calendar that cannot be reached is
    unknown, and unknown must not read as "no earnings tonight".
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _post(payload: dict, session: str | None = None,
          endpoint: str | None = None, timeout: int | None = None) -> tuple[dict, str]:
    headers = {"Content-Type": "application/json", "User-Agent": _UA,
               "Accept": "application/json, text/event-stream"}
    if session:
        headers["mcp-session-id"] = session
    req = urllib.request.Request(endpoint or ENDPOINT,
                                 data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as resp:
        return dict(resp.headers), resp.read().decode()


def _unframe(text: str) -> dict:
    """SSE frames or plain JSON, whichever the server felt like sending.

    Detected by the presence of `data:` lines rather than by the first token. One
    of these services opens the stream with an SSE comment - `: ping - <time>` -
    before the message frame, so a startswith("event:") check reads the whole
    stream as JSON and fails on the colon.
    """
    lines = text.splitlines()
    data = [line[6:] for line in lines if line.startswith("data: ")]
    if data:
        text = "".join(data)
    return json.loads(text) if text.strip() else {}


def call(tool: str, arguments: dict | None = None, retries: int = RETRIES,
         endpoint: str | None = None, timeout: int | None = None) -> object:
    """One tool call, with its own session. Raises McpUnavailable, never guesses.

    A tool may answer with an object or a list - `news_feed` returns one
    envelope per source - so the return type is deliberately not `dict`.
    """
    last = "not attempted"
    for attempt in range(retries):
        try:
            return _once(tool, arguments, endpoint, timeout)
        except McpUnavailable as exc:
            last = exc.reason
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise McpUnavailable(last)


def _once(tool: str, arguments: dict | None,
          endpoint: str | None = None, timeout: int | None = None) -> object:
    try:
        headers, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                                       "clientInfo": {"name": "ballast",
                                                      "version": "1"}}},
                           endpoint=endpoint, timeout=timeout)
        session = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        if not session:
            raise McpUnavailable("initialize returned no session id")
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session,
              endpoint, timeout)
        _, body = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": tool,
                                    "arguments": arguments or {}}}, session, endpoint,
                        timeout)
    except urllib.error.HTTPError as exc:
        raise McpUnavailable(f"HTTP {exc.code} from {endpoint or ENDPOINT}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise McpUnavailable(f"{type(exc).__name__}: {exc}") from exc

    try:
        payload = _unframe(body)
    except json.JSONDecodeError as exc:
        raise McpUnavailable(f"unparseable response: {exc}") from exc
    if "error" in payload:
        raise McpUnavailable(str(payload["error"])[:200])
    content = (payload.get("result") or {}).get("content") or []
    if not content:
        raise McpUnavailable("response carried no content")
    text = content[0].get("text", "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}
    # The tool answers 200 and wraps the upstream's own status. A 503 body that
    # parses cleanly would otherwise be handed back as data, and an empty result
    # would read as "no earnings scheduled tonight" - absence of evidence dressed
    # as evidence of absence, on the one input the whole policy rests on.
    if isinstance(data, dict) and data.get("success") is False:
        raise McpUnavailable(
            f"upstream {data.get('status_code', '?')}: {str(data.get('error'))[:120]}")
    return data




def query(entry_id: str, **params) -> object:
    """`entry_id`, not `id`, and the params nested. Flat arguments come back as
    a pydantic validation error rather than a result."""
    return call("do_query", {"entry_id": entry_id, "params": params})


def underlying(ticker: str) -> dict:
    """Where the listed US share last traded, or why that is not known.

    Never raises and never guesses. A caller gets either a priced reference or
    `available: False` with the reason, because an exit cost quoted against a
    reference this module invented would be worse than no reference at all.
    """
    out: dict = {"available": False, "source": "bitget-mcp-server",
                 "entry": "equity_price_quote", "ticker": ticker}
    try:
        body = query("equity_price_quote", symbol=ticker)
    except McpUnavailable as exc:
        out["reason"] = str(exc)
        return out
    except Exception as exc:  # BLE001 is ignored here: reported, never swallowed
        out["reason"] = f"{type(exc).__name__}: {exc}"
        return out

    data = body.get("data") if isinstance(body, dict) else None
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        out["reason"] = "the Skill answered with no rows for this ticker"
        return out

    row = rows[0]
    last = row.get("last_price")
    if not isinstance(last, (int, float)) or last <= 0:
        out["reason"] = "the Skill returned no usable last price"
        return out

    out.update(available=True, last_price=float(last),
               bid=row.get("bid"), ask=row.get("ask"),
               printed_at=row.get("last_timestamp"))
    return out


def basis_bp(token_price: float, share_price: float) -> float:
    """How far the token sits from the share, in basis points.

    Positive means the token is marked above the share. This treats 1 USDT as
    1 USD; the caller has to say so, because it is an assumption and not a
    measurement.
    """
    return (token_price - share_price) / share_price * 10_000.0
