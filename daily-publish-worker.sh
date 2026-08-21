#!/bin/sh
# Long-running worker for Eat The Bible 120.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
PYTHON=${PYTHON:-/usr/bin/python3}

exec 9>"$ROOT/.daily-publish.lock"
flock -n 9 || {
  printf '%s\n' 'A daily publish worker is already running; exiting.'
  exit 0
}

sync_audio() {
  mkdir -p "$ROOT/audio"
  for source in "$ROOT"/day-*.mp3; do
    [ -e "$source" ] || continue
    filename=$(basename "$source")
    destination="$ROOT/audio/$filename"
    if [ -e "$destination" ]; then
      printf 'Refusing to overwrite existing %s\n' "$destination" >&2
      exit 1
    fi
    mv "$source" "$destination"
    printf 'Moved %s into audio/\n' "$filename"
  done
}

# Publish any episode left behind by an interrupted or completed worker.
sync_audio
next_day=$($PYTHON -c 'import json; print(json.load(open("sequence-state.json"))["next_day"])')
if [ "$next_day" -le 120 ]; then
  "$PYTHON" generate_next_episode.py worker
fi

# The generator writes to the repository root; GitHub Pages serves audio/.
sync_audio
./publish.sh
