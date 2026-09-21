"""Regenerate tools/fixtures/answers.json from the desk itself.

The shape test says "regenerate tools/fixtures/answers.json" and there was
nothing to run. Hand-maintaining the shape of a four-case fixture against a
function that grows keys is how the browser gate goes green while the real
panel is broken - which is the exact failure that test exists to catch.

    python3 tools/regen_fixtures.py          # rewrite
    python3 tools/regen_fixtures.py --check  # fail if stale (CI)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import desk, llm, market, mcp

OUT = Path(__file__).resolve().parent / "fixtures" / "answers.json"

# Imported, not restated. The first cut of this script declared its own SPEC,
# LISTED and BOOK, guessed the instrument shape wrong, and wrote four identical
# error answers - a generator that silently produces the wrong fixture is worse
# than no generator, since the shape test then passes against nonsense.

# The panel has to render both a present reference and an absent one, so the
# priced case carries a real-shaped one and the rest carry the refusal.
PRESENT = {"available": True, "source": "bitget-mcp-server",
           "entry": "equity_price_quote", "ticker": "TSLA",
           "last_price": 364.18, "bid": 364.18, "ask": 364.19,
           "printed_at": "2026-09-18T23:59:58.183801Z",
           "token_price": 369.5, "basis_bp": 146.0, "hours_since_print": 57.0}
ABSENT = {"available": False, "source": "bitget-mcp-server",
          "entry": "equity_price_quote", "ticker": "TSLA",
          "reason": "the Skill answered with no rows for this ticker"}


def produce(book: dict, reference: dict, spec: dict, listed: dict) -> dict:
    desk._UNIVERSE_CACHE[0] = None
    with mock.patch.object(llm, "compile_question", return_value=spec), \
         mock.patch.object(mcp, "underlying", return_value=dict(reference)), \
         mock.patch.object(market, "depth_or_touch", **book):
        return desk.answer("cost to exit 40000 USDT of TSLA", listed)


def build() -> dict:
    # Imported here rather than at module scope: it needs the sys.path line
    # below, and a deferred import is cleaner than suppressing E402.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    from test_desk import BOOK, LISTED, SPEC

    return {
        "priced": produce({"return_value": (*BOOK, "orderbook")},
                          PRESENT, SPEC, LISTED),
        "floor": produce({"return_value": ([[358.0, 1.0]], [[358.5, 1.0]],
                                           "touch")}, ABSENT, SPEC, LISTED),
        "unquotable": produce({"return_value": ([], [], "none")},
                              ABSENT, SPEC, LISTED),
        "error": produce({"side_effect": market.MarketUnavailable("http 503")},
                         ABSENT, SPEC, LISTED),
    }


def main() -> int:
    wanted = build()
    if "--check" in sys.argv:
        current = json.loads(OUT.read_text())
        if {k: set(v) for k, v in current.items()} != \
           {k: set(v) for k, v in wanted.items()}:
            print("tools/fixtures/answers.json is stale; run "
                  "python3 tools/regen_fixtures.py", file=sys.stderr)
            return 1
        print(f"fixtures current: {', '.join(sorted(wanted))}")
        return 0
    OUT.write_text(json.dumps(wanted, indent=1, sort_keys=True) + "\n")
    print(f"rewrote {OUT.name} - {', '.join(sorted(wanted))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
