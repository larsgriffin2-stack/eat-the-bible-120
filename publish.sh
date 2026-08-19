#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

# The production repository uses the dedicated deploy key created for GitHub Pages.
if [ -f /opt/data/.ssh/id_ed25519 ]; then
  export GIT_SSH_COMMAND="ssh -i /opt/data/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes"
fi

python3 generator.py

git add audio cover.jpg rss.xml generator.py README.md publish.sh daily-publish.sh .gitignore .nojekyll
if git diff --cached --quiet; then
  echo "No podcast changes to commit."
  exit 0
fi

STAMP=$(date -u '+%Y-%m-%d %H:%M UTC')
git commit -m "Publish podcast update: $STAMP"
git push origin main
