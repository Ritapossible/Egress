"""Freeze one complete research task, as a judge with JavaScript off would need it.

The desk is the product and it lives behind JavaScript and a POST. That is the
right design for a live tool and the wrong one for a submission: `/ask` is a
404, the homepage says it "needs JavaScript and a configured reader", and a
judge who browses with scripts disabled - or who simply reads the repo - never
sees the thing being judged do its job.

So one real task is captured and written into the page as static HTML.

IT IS A RECORDING, NOT A RE-RUN. The figures below are whatever the live desk
answered at the timestamp stored beside them, against that moment's book. They
are deliberately not refreshed by the crawl: a number that moves every twenty
minutes cannot be checked by a reader, and the claim being made here is "this
question was asked and this is what came back", which is a claim about one
moment.

TWO NAMES, CHOSEN TO DISAGREE. A liquid one where the book fills the whole
order, and a thin one where it does not and the answer has to degrade to a
floor. One example proves the happy path; the pair proves the desk knows the
difference.

    python3 tools/freeze_task.py                  # -> state/research_task.json
    python3 tools/freeze_task.py --local          # call desk.answer directly
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "state" / "research_task.json"
ENDPOINT = "https://egress-v1.vercel.app/api/ask"

# The liquid case and the thin case. Whichever way the venue's books move, one
# of these should fill and one should not.
TASKS = (
    ("liquid", "what does leaving 40k of TSLA cost?"),
    ("thin", "what does leaving 5k of RIOT cost?"),
)


def _live(question: str) -> dict:
    body = json.dumps({"q": question}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "egress-freeze"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def _local(question: str) -> dict:
    from egress import desk
    return desk.answer(question)


def build(local: bool = False) -> Path:
    ask = _local if local else _live
    captured = []
    for kind, question in TASKS:
        answer = ask(question)
        captured.append({"kind": kind, "question": question, "answer": answer})
    payload = {
        "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "desk.answer()" if local else ENDPOINT,
        "note": ("A recording of one moment, not a live figure. The book it was "
                 "priced against has moved since."),
        "tasks": captured,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return OUT


if __name__ == "__main__":
    path = build(local="--local" in sys.argv)
    d = json.loads(path.read_text())
    print(f"wrote {path.name} ({path.stat().st_size:,} bytes) from {d['source']}")
    for task in d["tasks"]:
        answer = task["answer"]
        head = answer.get("headline") or answer.get("error") or "?"
        print(f"  {task['kind']:7} {answer.get('symbol', '-'):12} {head[:90]}")
