#!/bin/sh
# Launch the long-running daily generation/publish worker and return quickly
# so Hermes cron does not time out while LocalAI renders the episode.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LOCK="$ROOT/.daily-publish-launch.lock"
WORKER="$ROOT/daily-publish-worker.sh"
CATCHUP_MARKER="$ROOT/.catchup-active"

# The two-hour catch-up loop owns the schedule while it is active.
if [ -f "$CATCHUP_MARKER" ]; then
  catchup_pid=$(cat "$CATCHUP_MARKER" 2>/dev/null || true)
  if [ -n "$catchup_pid" ] && kill -0 "$catchup_pid" 2>/dev/null; then
    printf 'Two-hour catch-up publisher is active (pid %s); skipping daily launch.\n' "$catchup_pid"
    exit 0
  fi
  rm -f "$CATCHUP_MARKER"
fi

exec 9>"$LOCK"
flock -n 9 || {
  printf '%s\n' 'A daily publish worker is already being launched; exiting.'
  exit 0
}

# If a worker already owns the processing lock, do not launch another one.
exec 8>"$ROOT/.daily-publish.lock"
if ! flock -n 8; then
  printf '%s\n' 'A daily publish worker is already running; exiting.'
  exit 0
fi
flock -u 8

nohup setsid "$WORKER" >>"$ROOT/generation.log" 2>&1 </dev/null &
printf 'Started detached daily publish worker (pid %s).\n' "$!"
