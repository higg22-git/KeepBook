#!/bin/bash
# start-keepbook.command — one-click launcher for KeepBook.
#
# Starts the KeepBook backend (uvicorn on :8100) as a *transient launchd
# service* and opens the UI in a Chrome app-mode window. Safe to double-click
# from Finder / the Dock, or run from Terminal.
#
# Why launchd and not `nohup`: a Finder/Dock launch puts this script in a
# process group that macOS reaps the instant the applet exits — a nohup'd
# child dies in <2s. A launchd service is owned by launchd, not us, so it
# outlives the applet. (Learned the hard way on this machine, macOS 26.)
#
# Behaviour:
#   * If a healthy KeepBook is already on the port, ADOPT it (just open the
#     window). Never restart a running server — the demo may be live on it.
#   * Only seeds demo state (backend/state.json + uploads) when state.json is
#     missing AND nothing healthy is on the port. Otherwise state is untouched.
#   * Health-polls http://localhost:PORT/health for {"status":"ok"} up to ~20s
#     before opening; opens anyway on timeout and says so.
#   * Ollama is assumed already running (menu-bar app). We never start/stop it;
#     if it's down, KeepBook still starts and shows its own outage banner.
#
# Port override for testing: KEEPBOOK_PORT=8115 ./start-keepbook.command

# --- 1. PATH bootstrap -------------------------------------------------------
# Finder-launched apps inherit a minimal PATH (no /opt/homebrew/bin). Set an
# explicit one so tools resolve. We otherwise use absolute paths throughout.
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"

set -u

# --- 2. Resolve paths (absolute, no reliance on cwd) -------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
EVAL_DIR="$REPO_ROOT/eval"
UPLOADS_DIR="$BACKEND_DIR/uploads"
VENV_PY="$BACKEND_DIR/.venv/bin/python"
RUN_DIR="$SCRIPT_DIR/.run"

PORT="${KEEPBOOK_PORT:-8100}"
if [ "$PORT" = "8100" ]; then
  LABEL="com.keepbook.server"
  LOG="$RUN_DIR/uvicorn.log"
else
  LABEL="com.keepbook.server.$PORT"
  LOG="$RUN_DIR/uvicorn-$PORT.log"
fi
PLIST="$RUN_DIR/$LABEL.plist"
HEALTH_URL="http://localhost:$PORT/health"
UI_URL="http://localhost:$PORT"
UID_NUM="$(id -u)"

mkdir -p "$RUN_DIR"

# --- 3. Helpers --------------------------------------------------------------
# Print the /health body on stdout and return 0 iff it says status:ok.
health_body() {
  local body
  body="$(/usr/bin/curl -fsS --max-time 2 "$HEALTH_URL" 2>/dev/null)" || return 1
  case "$body" in
    *'"status":"ok"'*|*'"status": "ok"'*) printf '%s' "$body"; return 0 ;;
    *) return 1 ;;
  esac
}

# Open the UI: prefer Chrome app-mode, fall back to the default browser.
open_ui() {
  local chrome="" cand
  for cand in \
    "/Applications/Google Chrome.app" \
    "$HOME/Applications/Google Chrome.app"; do
    if [ -d "$cand" ]; then chrome="$cand"; break; fi
  done
  if [ -n "$chrome" ]; then
    echo "Opening Chrome app-mode window -> $UI_URL"
    /usr/bin/open -na "Google Chrome" --args --app="$UI_URL" \
      || /usr/bin/open "$UI_URL"
  else
    echo "Chrome not found; opening default browser -> $UI_URL"
    /usr/bin/open "$UI_URL"
  fi
}

echo "KeepBook launcher — port $PORT, label $LABEL"

# --- 4. ADOPT: if a healthy server is already up, just open the window -------
if BODY="$(health_body)"; then
  echo "ADOPT: healthy KeepBook already running on :$PORT — not restarting."
  echo "  /health -> $BODY"
  open_ui
  echo "Done (adopted)."
  exit 0
fi

echo "No healthy server on :$PORT — starting one."

# --- 5. Sanity: venv python must exist ---------------------------------------
if [ ! -x "$VENV_PY" ]; then
  echo "ERROR: backend venv python not found at $VENV_PY" >&2
  echo "       Create it: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# --- 6. Seed demo state ONLY if state.json is missing ------------------------
# demo_state.sh also restarts uvicorn via nohup, which would fight our launchd
# service for the port — so we inline just the state+image staging here and
# never call it. In practice state.json already exists, so this is defensive.
STATE_JSON="$BACKEND_DIR/state.json"
if [ ! -f "$STATE_JSON" ]; then
  echo "state.json missing — seeding demo state (state.demo.json + uploads)."
  if [ -f "$BACKEND_DIR/state.demo.json" ]; then
    /bin/cp "$BACKEND_DIR/state.demo.json" "$STATE_JSON"
    echo "  backend/state.json <- state.demo.json"
  else
    echo "  WARNING: state.demo.json missing; app will use its own defaults." >&2
  fi
  /bin/mkdir -p "$UPLOADS_DIR"
  IMAGE_MANIFEST="
doc_001:testset/1099int_clean_01.png
doc_002:testset/1098_clean_01.png
doc_003:testset/w2_clean_02.png
doc_004:w2_test.png
doc_005:testset/receipt_01.png
doc_006:testset/1099int_clean_02.png
doc_007:testset/k1_clean_01.png
doc_101:testset/w2_clean_01.png
doc_102:testset/w2_photo_01.png
doc_103:testset/1099nec_clean_01.png
doc_104:testset/1099nec_clean_02.png
doc_105:testset/1099int_photo_01.png
doc_106:testset/1099int_photo_02.png
doc_107:testset/1098_clean_02.png
doc_108:testset/k1_clean_02.png
doc_109:testset/k1_photo_01.png
doc_110:testset/k1_photo_02.png
doc_111:testset/1099nec_clean_03.png
doc_112:testset/1099nec_photo_01.png
doc_113:testset/1099int_clean_02.png
doc_114:testset/1099int_clean_02.png
doc_115:testset/k1_clean_01.png
doc_116:testset/w2_photo_02.png
doc_117:testset/1099int_photo_01.png
doc_118:testset/1099nec_photo_02.png
"
  echo "  staging images into $UPLOADS_DIR ..."
  while IFS=: read -r doc_id rel; do
    [ -z "$doc_id" ] && continue
    src="$EVAL_DIR/$rel"
    dst="$UPLOADS_DIR/${doc_id}.png"
    [ -f "$src" ] && /bin/cp "$src" "$dst"
  done <<EOF
$IMAGE_MANIFEST
EOF
else
  echo "state.json present — leaving it untouched."
fi

# --- 7. (Re)write the launchd plist ------------------------------------------
# WorkingDirectory=backend so main.py loads backend/state.json. Absolute python.
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV_PY</string>
    <string>-m</string>
    <string>uvicorn</string>
    <string>main:app</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$BACKEND_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
EOF

# --- 8. Bootstrap the service (bootout any stale copy / free the port) -------
/bin/launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
STALE_PIDS="$(/usr/sbin/lsof -ti "tcp:$PORT" 2>/dev/null || true)"
if [ -n "$STALE_PIDS" ]; then
  echo "clearing stale process on :$PORT (pid $STALE_PIDS)"
  kill $STALE_PIDS 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    /usr/sbin/lsof -ti "tcp:$PORT" >/dev/null 2>&1 || break
    sleep 0.25
  done
fi

echo "bootstrapping launchd service $LABEL ..."
if /bin/launchctl bootstrap "gui/$UID_NUM" "$PLIST"; then
  echo "  service bootstrapped."
else
  echo "  WARNING: launchctl bootstrap returned nonzero — continuing to health poll." >&2
fi

# --- 9. Health poll (~20s) ---------------------------------------------------
echo "waiting for KeepBook to answer on $HEALTH_URL ..."
UP=0
for _ in $(seq 1 40); do
  if BODY="$(health_body)"; then UP=1; break; fi
  sleep 0.5
done

if [ "$UP" = "1" ]; then
  echo "KeepBook is up:"
  echo "  /health -> $BODY"
else
  echo "WARNING: KeepBook did not report healthy within ~20s." >&2
  echo "         Opening the window anyway; check log: $LOG" >&2
fi

# --- 10. Open the UI ---------------------------------------------------------
open_ui
echo "Done. To stop: run stop-keepbook.command (or Stop KeepBook.app)."
