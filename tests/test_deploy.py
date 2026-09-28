"""What Vercel is asked to deploy, checked before Vercel refuses it.

Every production deployment failed from 2026-09-28 02:47Z:

    Total bundle size (228.11 MB) exceeds the maximum function size

Nothing about the site had changed. `state/snapshots/` - one gzipped CSV per
day of raw crawl output, never read at request time - had grown to 209 MB and
carried the function bundle over the limit. The site went stale for six hours
and the only signal was an email.

The project has no runtime dependencies, so the bundle is data, and data here
grows by roughly 15 MB a day on a schedule. That makes this a deadline, not an
accident: without a check it would have happened, and it will happen again the
moment something large is committed.

So the payload is measured here, from the git index, with `.vercelignore`
applied - no network, no Vercel, no deployment.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Vercel refused at 228 MB. The budget is far below that on purpose: this
# should fail while there is still a day to think about it, not at the wire.
BUDGET_MB = 50.0

# What the serverless function reads at request time. egress.desk and
# egress.llm between them open exactly these, and a deployment that ships
# neither answers every question wrongly rather than failing loudly - which is
# the note already standing at the top of desk.py.
RUNTIME_READS = ("state/universe.json", "state/symbol_marks.json")


def _patterns() -> list[str]:
    path = ROOT / ".vercelignore"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.startswith("#")]


def _excluded(rel: str, patterns: list[str]) -> bool:
    if "__pycache__" in rel:
        return True
    return any(rel == p or rel.startswith(p.rstrip("/") + "/")
               for p in patterns if not p.startswith("**"))


def _payload() -> list[tuple[int, str]]:
    """Every tracked file Vercel would receive, largest first."""
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    patterns = _patterns()
    rows = []
    for rel in listed.stdout.split():
        if _excluded(rel, patterns):
            continue
        f = ROOT / rel
        if f.exists():
            rows.append((f.stat().st_size, rel))
    return sorted(rows, reverse=True)


class TheDeploymentPayloadFitsInVercel(unittest.TestCase):
    def test_the_payload_is_under_budget(self) -> None:
        rows = _payload()
        total = sum(size for size, _ in rows) / 1048576
        worst = "\n  ".join(f"{s / 1048576:.2f} MB  {r}" for s, r in rows[:5])
        self.assertLess(
            total, BUDGET_MB,
            f"the deployment payload is {total:.1f} MB against a {BUDGET_MB:.0f} MB "
            f"budget; Vercel refused this build at 228 MB. Largest:\n  {worst}",
        )

    def test_the_crawl_archive_is_not_deployed(self) -> None:
        """It is the thing that broke this, and it grows on a schedule."""
        self.assertIn("state/snapshots", _patterns(),
                      "state/snapshots is raw crawl output, is never read at "
                      "request time, and grows ~15 MB a day")

    def test_the_site_itself_is_not_excluded(self) -> None:
        """The opposite mistake: docs/ is the outputDirectory."""
        patterns = _patterns()
        for rel in ("docs/index.html", "api/ask.py", "vercel.json"):
            with self.subTest(path=rel):
                self.assertFalse(_excluded(rel, patterns),
                                 f"{rel} must reach the deployment")

    def test_what_the_function_reads_still_ships(self) -> None:
        patterns = _patterns()
        deployed = {rel for _, rel in _payload()}
        for rel in RUNTIME_READS:
            with self.subTest(path=rel):
                self.assertFalse(_excluded(rel, patterns),
                                 f"{rel} is read on every request")
                self.assertIn(rel, deployed,
                              f"{rel} is read on every request and is not in "
                              f"the deployment")


if __name__ == "__main__":
    unittest.main()
