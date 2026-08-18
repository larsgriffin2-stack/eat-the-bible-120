#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
python3 generator.py

git add audio rss.xml generator.py README.md .nojekyll
if git diff --cached --quiet; then
  echo "No podcast changes to commit."
  exit 0
fi

STAMP=$(date -u '+%Y-%m-%d %H:%M UTC')
git commit -m "Publish podcast update: $STAMP"
git push origin main
