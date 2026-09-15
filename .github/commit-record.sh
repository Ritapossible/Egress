#!/usr/bin/env bash
# Rebuild the site from the record, then commit and push both.
#
# Run repeatedly while the crawler is still writing, so every step has to be
# safe to retry and safe to fail. Never `set -e` past the rebuild: a failed
# commit cycle must not take down the crawl that is still collecting.
set -uo pipefail

# The page states the record, so it is rebuilt whenever the record moves.
# Without this the hosted site silently freezes at the last generation - stale
# figures nobody notices, which is the failure MEMORY.md rule 5 exists to
# prevent. A build failure is REPORTED rather than swallowed: `|| true` here is
# what let an empty evidence table ship behind a fresh-looking commit.
if ! python -m egress.page; then
  echo "::error::page build failed - committing the record without rebuilding"
fi

git add -A state/ docs/
if git diff --cached --quiet; then
  echo "nothing to commit"
  exit 0
fi

git stash push --staged -m pending || { echo "::warning::stash failed"; exit 0; }
git pull --rebase --autostash origin main || echo "::warning::pull failed; committing anyway"

if ! git stash pop; then
  # Conflict markers must never reach the record. Take the incoming record
  # (append-only, so the remote already has everything we do) and let the next
  # cycle rebuild the pages on top of it.
  echo "::warning::stash pop conflicted; keeping the remote record"
  git checkout --theirs -- state/ 2>/dev/null || true
  git checkout --ours   -- docs/  2>/dev/null || true
  git stash drop || true
  git reset --hard origin/main
  exit 0
fi

git add -A state/ docs/
git diff --cached --quiet && exit 0

# A conflict marker in a committed file is worse than a missed commit.
if git diff --cached | grep -qE '^\+(<<<<<<<|>>>>>>>|=======$)'; then
  echo "::error::conflict markers in the staged diff - refusing to commit"
  git reset
  exit 1
fi

git commit -m "crawl: $(date -u '+%Y-%m-%d %H:%MZ')" || exit 0
for i in 1 2 3; do
  git push && exit 0
  sleep $((i * 5))
  git pull --rebase --autostash origin main || true
done
echo "::error::push failed after 3 attempts; the next cycle will retry"
exit 1
