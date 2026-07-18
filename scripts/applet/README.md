# KeepBook Dock applet

One-click start/stop for KeepBook (backend uvicorn on :8100 + UI in a Chrome app window).

- **`start-keepbook.command`** — starts the backend as a transient launchd service, health-polls `http://localhost:8100/health`, then opens the UI. If a healthy KeepBook is already on :8100 it *adopts* it (no restart). Never touches Ollama.
- **`stop-keepbook.command`** — boots out the service and frees the port (leaves Ollama running).
- **`build-applets.sh`** — run once to generate `KeepBook.app` + `Stop KeepBook.app` (osacompile wrappers around the `.command` files, icon built from `frontend/assets/logo-mark.svg`). The `.app` bundles are **not committed** (machine-generated Mach-O) — regenerate with this script, then **drag `KeepBook.app` to the Dock**.
- **Debugging** — launchd label: `com.keepbook.server` (`launchctl print gui/$(id -u)/com.keepbook.server`). Server log: `scripts/applet/.run/uvicorn.log`. Test on another port without touching the demo: `KEEPBOOK_PORT=8115 ./start-keepbook.command` (label `com.keepbook.server.8115`).
