#!/bin/sh
# Generate the next Eat The Bible 120 episode, move it into audio/,
# regenerate the RSS feed, and publish the update to GitHub.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
PYTHON=${PYTHON:-/usr/bin/python3}

# Prevent overlapping scheduled runs.
exec 9>"$ROOT/.daily-publish.lock"
flock -n 9 || {
  printf '%s\n' 'A daily publish run is already in progress; exiting.'
  exit 0
}

sync_audio() {
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

# Recover any episode produced by an earlier run before publishing.
sync_audio

next_day=$($PYTHON -c 'import json; print(json.load(open("sequence-state.json"))["next_day"])')
if [ "$next_day" -le 120 ]; then
  "$PYTHON" generate_next_episode.py worker
fi

# The generator writes to the repository root; GitHub Pages serves audio/.
sync_audio
./publish.sh
