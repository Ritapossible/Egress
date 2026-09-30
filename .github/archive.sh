#!/usr/bin/env bash
# The raw crawl archive, kept in this repository but off the deployed branch.
#
# state/snapshots/ is one gzipped CSV per UTC day. It reached 209 MB and took
# Vercel's function bundle to 228.11 MB, over the limit, and every production
# deployment failed for six hours on 2026-09-28. .vercelignore stopped it
# reaching the bundle; this stops it reaching main's tree at all, so the
# deployment clones ~3 MB instead of ~220 MB and stops growing by 15 MB a day.
#
# It goes to an orphan branch in THIS repository rather than to a release
# asset or an object store, for one reason: the record has to stay clonable.
# Every figure on the site is derived from these rows, and "git clone, git
# checkout data, re-run the study" is the claim. A bucket nobody can read
# without a key would trade a deployment problem for a much worse one. The
# commits are still GitHub-timestamped, so they are still evidence of when a
# reading was taken.
#
#   archive.sh restore   put the archive into state/snapshots (start of a run)
#   archive.sh publish   push what is on disk to the data branch
#
# Both are safe to retry and safe to fail. gzip members concatenate, so each
# day's file on disk always holds that whole day: a failed publish costs
# nothing that the next publish does not carry, and the exposure is the same
# as it was when these files rode on main.
set -uo pipefail

BRANCH="${ARCHIVE_BRANCH:-data}"
DIR="state/snapshots"
WORKTREE="${RUNNER_TEMP:-/tmp}/egress-archive"

have_remote_branch() {
  git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1
}

restore() {
  mkdir -p "$DIR"
  if ! have_remote_branch; then
    echo "archive: no '$BRANCH' branch yet - nothing to restore"
    return 0
  fi
  git fetch --depth=1 origin "$BRANCH" || { echo "::error::archive fetch failed"; return 1; }
  # --worktree only: never touches main's index, so these files cannot be
  # staged onto the deployed branch by a later `git add -A state/`.
  git restore --source=FETCH_HEAD --worktree -- "$DIR" || {
    echo "::error::archive restore failed"; return 1; }
  echo "archive: restored $(ls -1 "$DIR" 2>/dev/null | wc -l) day file(s) from '$BRANCH'"
}

# Copy this run's own files into the worktree and stage exactly those, by name.
# Never `add -A` over the worktree: it also holds whatever the branch tip had,
# and re-adding a file this run does not hold would write a stale copy over
# another writer's newer one.
stage_ours() {
  local names=() f
  mkdir -p "$WORKTREE/$DIR"
  for f in "$DIR"/*.csv.gz; do
    [ -e "$f" ] || continue
    cp -f "$f" "$WORKTREE/$DIR/"
    names+=("$DIR/$(basename "$f")")
  done
  if [ -f state/manifest.jsonl ]; then
    cp -f state/manifest.jsonl "$WORKTREE/state/"
    names+=(state/manifest.jsonl)
  fi
  [ "${#names[@]}" -gt 0 ] || return 0
  (cd "$WORKTREE" && git add -f -- "${names[@]}")
}

publish() {
  [ -d "$DIR" ] || { echo "archive: nothing on disk"; return 0; }
  rm -rf "$WORKTREE"
  if have_remote_branch; then
    git fetch --depth=1 origin "$BRANCH" || { echo "::warning::archive fetch failed"; return 1; }
    git worktree add --detach "$WORKTREE" FETCH_HEAD >/dev/null 2>&1 || {
      echo "::warning::archive worktree failed"; return 1; }
  else
    # First publish: an orphan tree with no history to inherit.
    git worktree add --detach --no-checkout "$WORKTREE" >/dev/null 2>&1 || {
      echo "::warning::archive worktree failed"; return 1; }
    git -C "$WORKTREE" checkout --orphan "$BRANCH" >/dev/null 2>&1 || true
    git -C "$WORKTREE" reset >/dev/null 2>&1 || true
  fi

  # The manifest rides along so the branch is self-describing: a clone of it
  # alone can say which snapshots these rows are supposed to contain. Staged
  # with -f because main's .gitignore lists state/snapshots.
  stage_ours || { echo "::warning::archive staging failed"; return 1; }
  if git -C "$WORKTREE" diff --cached --quiet; then
    echo "archive: unchanged"
    git worktree remove --force "$WORKTREE" 2>/dev/null || true
    return 0
  fi
  git -C "$WORKTREE" commit -q -m "archive: $(date -u '+%Y-%m-%d %H:%MZ')" || {
    echo "::warning::archive commit failed"; return 1; }

  local ok=1
  for i in 1 2 3; do
    if git -C "$WORKTREE" push origin "HEAD:$BRANCH"; then ok=0; break; fi
    sleep $((i * 5))
    # Someone else moved the branch. Build on top of what landed rather than
    # beside it. This used to fetch in the main repo, `reset --soft` in the
    # worktree - which reads the worktree's own FETCH_HEAD, not the one just
    # fetched - and then `commit --amend`, which rewrites a commit instead of
    # adding one. Every retry was therefore non-fast-forward and rejected;
    # reproduced with a second writer landing first, three rejections in a row
    # and the new rows never arriving. It never bit because the crawl is the
    # only writer, but a retry that cannot succeed is not a retry.
    #
    # Now: fetch IN the worktree, move it to the new tip, stage only the files
    # this run holds (stage_ours), and make a new commit on top. A file only the
    # other writer has keeps their version - not a deletion, not a stale copy.
    git -C "$WORKTREE" fetch --depth=1 origin "$BRANCH" 2>/dev/null || continue
    git -C "$WORKTREE" reset -q --hard FETCH_HEAD 2>/dev/null || continue
    stage_ours || continue
    git -C "$WORKTREE" diff --cached --quiet && { ok=0; break; }
    git -C "$WORKTREE" commit -q -m "archive: $(date -u '+%Y-%m-%d %H:%MZ')" || continue
  done
  git worktree remove --force "$WORKTREE" 2>/dev/null || true
  [ "$ok" = 0 ] || echo "::warning::archive push failed; the next cycle carries the same days"
  return "$ok"
}

case "${1:-}" in
  restore) restore ;;
  publish) publish ;;
  *) echo "usage: archive.sh {restore|publish}" >&2; exit 2 ;;
esac
