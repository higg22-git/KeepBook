#!/bin/bash
# stop-keepbook.command — stop KeepBook started by start-keepbook.command.
#
# Boots out the transient launchd service and, best-effort, kills any uvicorn
# still holding the port. Does NOT touch Ollama (it's a separate menu-bar app).
# Safe to double-click from Finder / the Dock, or run from Terminal.
#
# Port override for testing: KEEPBOOK_PORT=8115 ./stop-keepbook.command

export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$SCRIPT_DIR/.run"

PORT="${KEEPBOOK_PORT:-8100}"
if [ "$PORT" = "8100" ]; then
  LABEL="com.keepbook.server"
else
  LABEL="com.keepbook.server.$PORT"
fi
PLIST="$RUN_DIR/$LABEL.plist"
UID_NUM="$(id -u)"

echo "Stopping KeepBook — port $PORT, label $LABEL"

# 1. Bootout the launchd service (by label; fall back to plist path).
if /bin/launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
  echo "  launchd service $LABEL booted out."
elif [ -f "$PLIST" ] && /bin/launchctl bootout "gui/$UID_NUM" "$PLIST" >/dev/null 2>&1; then
  echo "  launchd service booted out (via plist)."
else
  echo "  no launchd service $LABEL was loaded (nothing to bootout)."
fi

# 2. Best-effort: kill any uvicorn still holding the port.
PIDS="$(/usr/sbin/lsof -ti "tcp:$PORT" 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  echo "  killing process(es) still on :$PORT -> $PIDS"
  kill $PIDS 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8; do
    /usr/sbin/lsof -ti "tcp:$PORT" >/dev/null 2>&1 || break
    sleep 0.25
  done
  # Escalate if still stubborn.
  PIDS="$(/usr/sbin/lsof -ti "tcp:$PORT" 2>/dev/null || true)"
  if [ -n "$PIDS" ]; then
    echo "  forcing (SIGKILL) $PIDS"
    kill -9 $PIDS 2>/dev/null || true
  fi
fi

if /usr/sbin/lsof -ti "tcp:$PORT" >/dev/null 2>&1; then
  echo "WARNING: something is still listening on :$PORT." >&2
else
  echo "Port :$PORT is free. KeepBook stopped. (Ollama left running.)"
fi
