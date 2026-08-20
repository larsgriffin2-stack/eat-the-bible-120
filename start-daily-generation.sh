#!/bin/sh
set -eu
# Compatibility wrapper. Scheduling must use daily-publish.sh so generation
# and publication are one locked, idempotent transaction.
exec '/opt/data/Eat The Bible 120/daily-publish.sh'
