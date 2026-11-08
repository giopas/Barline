#!/bin/bash
# Publish wiki/ to the GitHub wiki (a separate git repo: <repo>.wiki.git).
#
#   tools/publish_wiki.sh            # copy wiki/*.md over, commit, push
#   tools/publish_wiki.sh --check    # only say whether the published wiki matches wiki/
#
# Part of the release checklist (WORKPLAN.md): run it after pushing main
# whenever anything in wiki/ changed -- a release, or a docs-only change.
# Pages are mirrored: a page deleted from wiki/ is deleted from the wiki too.
# Needs push access to the repo (the same login `git push` uses).
set -euo pipefail
cd "$(dirname "$0")/.."

WIKI_URL="https://github.com/giopas/SSP---Song-and-Setlist-Planner.wiki.git"
VERSION=$(python3 -c "import sys; sys.path.insert(0, 'server'); from version import VERSION; print(VERSION)")

if [ -n "$(git status --porcelain -- wiki)" ]; then
  echo "Note: wiki/ has changes that aren't committed; publishing them as they are." >&2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git clone -q --depth 1 "$WIKI_URL" "$tmp/wiki"

# mirror: remove published pages, then copy the current ones
find "$tmp/wiki" -maxdepth 1 -name '*.md' -delete
cp wiki/*.md "$tmp/wiki/"

cd "$tmp/wiki"
git add -A
if git diff --cached --quiet; then
  echo "The wiki is up to date."
  exit 0
fi
echo "Pages that differ from the published wiki:"
git diff --cached --name-status | sed 's/^/  /'
if [ "${1:-}" = "--check" ]; then
  echo "Run tools/publish_wiki.sh to publish them."
  exit 1
fi
git -c user.name="giopas" -c user.email="giopas@users.noreply.github.com" \
  commit -q -m "Wiki for $VERSION"
git push -q origin HEAD
echo "Published: https://github.com/giopas/SSP---Song-and-Setlist-Planner/wiki"
