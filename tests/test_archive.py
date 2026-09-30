"""The raw archive lives off main, and the build must notice when it is absent.

state/snapshots/ reached 209 MB and broke every Vercel deployment for six
hours. It now lives on the `data` branch - still in this repository, so the
record stays clonable and the figures stay reproducible, but off the branch
that gets deployed.

That introduces one new way to be wrong, and it is a quiet one. `store.days()`
reads the manifest, which stays on main; `read_day` returns nothing for a day
whose file is absent. So a checkout with no archive does not raise - it renders
every table from nothing while the footer goes on quoting the manifest's full
count. An empty site published behind a fresh-looking commit is worse than a
stale one, so the build has to refuse.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import store

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = "state/snapshots"


def _seed(root: Path, days: list[str], on_disk: list[str]) -> None:
    (root / "snapshots").mkdir(parents=True, exist_ok=True)
    lines = []
    for day in days:
        when = dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc)
        lines.append(json.dumps({"snap_ts": int(when.timestamp() * 1000),
                                 "file": f"{day}.csv.gz", "rows": 1}))
    (root / "manifest.jsonl").write_text("\n".join(lines) + "\n")
    for day in on_disk:
        with gzip.open(root / "snapshots" / f"{day}.csv.gz", "wt") as fh:
            fh.write("snap_ts,symbol\n")


class TheBuildNoticesAMissingArchive(unittest.TestCase):
    def test_a_complete_archive_reports_nothing_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root, ["2026-09-14", "2026-09-15"], ["2026-09-14", "2026-09-15"])
            self.assertEqual(store.missing_archive_days(root), [])

    def test_every_day_the_manifest_vouches_for_is_named(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root, ["2026-09-14", "2026-09-15", "2026-09-16"], ["2026-09-15"])
            missing = store.missing_archive_days(root)
            self.assertEqual([d.isoformat() for d in missing],
                             ["2026-09-14", "2026-09-16"])

    def test_an_empty_archive_is_not_mistaken_for_an_empty_record(self):
        """The failure this exists for: manifest full, snapshots/ empty."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root, ["2026-09-14", "2026-09-15"], [])
            self.assertEqual(len(store.missing_archive_days(root)), 2)
            # And the reader really does stay silent about it, which is why the
            # check cannot be left to the reader.
            self.assertEqual(store.read_day(dt.date(2026, 9, 14), root), [])

    def test_the_build_refuses_rather_than_publishing_nothing(self):
        from unittest import mock

        from egress import page
        with mock.patch.object(store, "missing_archive_days",
                               return_value=[dt.date(2026, 9, 14)]), \
                self.assertRaises(page.ArchiveIncomplete):
            page.write()


class TheArchiveIsWiredUp(unittest.TestCase):
    def test_the_archive_is_not_tracked_on_this_branch(self):
        listed = subprocess.run(["git", "ls-files", ARCHIVE], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        self.assertEqual(
            listed.stdout.strip(), "",
            "the archive is tracked on the deployed branch again; it grows "
            "~15 MB a day and took the Vercel bundle to 228 MB",
        )

    def test_git_would_not_pick_it_up_again(self):
        self.assertIn(f"{ARCHIVE}/", (ROOT / ".gitignore").read_text(),
                      "nothing stops `git add -A state/` re-adding the archive")

    def test_the_crawl_restores_it_before_building(self):
        flow = (ROOT / ".github" / "workflows" / "crawl.yml").read_text()
        self.assertIn("archive.sh restore", flow,
                      "the page build reads the whole record and the record "
                      "is not in the checkout until this runs")

    def test_the_rows_are_pushed_before_the_pages(self):
        """A reclaimed runner must lose pages, which rebuild, not rows, which cannot."""
        script = (ROOT / ".github" / "commit-record.sh").read_text()
        publish = script.find("archive.sh publish")
        self.assertNotEqual(publish, -1, "the archive is never published")
        push = script.find("git push", publish)
        self.assertNotEqual(push, -1, "no push follows the archive publish")
        self.assertLess(publish, push,
                        "main is pushed before the rows are safe")

    def test_a_failed_publish_does_not_fail_the_cycle(self):
        script = (ROOT / ".github" / "commit-record.sh").read_text()
        line = next(ln for ln in script.splitlines() if "archive.sh publish" in ln)
        self.assertIn("||", line,
                      "a failed publish must warn, not take down a crawl that "
                      "is still collecting; the next cycle carries the same days")


if __name__ == "__main__":
    unittest.main()
