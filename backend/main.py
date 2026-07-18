"""KeepBook backend — FastAPI, on-device tax-document intake.

Implements docs/API.md exactly, on port 8100. All model access goes through
backend/model_runtime.py via backend/pipeline.py. State is a single JSON file
(state.json) rewritten after every mutation, so restart == demo-safe.

Run:  uvicorn main:app --port 8100      (from backend/, venv active)
"""

import base64
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile as StarletteUploadFile

import pipeline

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
EVENTS_PATH = os.path.join(BASE_DIR, "events.jsonl")
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

os.makedirs(UPLOADS_DIR, exist_ok=True)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# ---------------------------------------------------------------------------
# In-memory state, guarded by a single lock. Serialized to STATE_PATH.
# documents/clients are dicts keyed by id (insertion order preserved).
# queue/processing are runtime-only (rebuilt from status on load).
# ---------------------------------------------------------------------------
STATE_LOCK = threading.RLock()
EVENTS_LOCK = threading.Lock()
WAKE = threading.Event()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_event(event: dict) -> None:
    """Append one pipeline event to events.jsonl (docs/API.md "Event log")."""
    row = {"ts": _now_iso(), **event}
    line = json.dumps(row) + "\n"
    with EVENTS_LOCK:
        with open(EVENTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(line)

STATE = {
    "documents": {},   # id -> Document
    "clients": {},     # id -> Client
    "seq_doc": 0,
    "seq_client": 0,
}
QUEUE = []             # pending doc ids awaiting processing
PROCESSING = None      # id currently being processed, or None


def _persist_locked() -> None:
    """Write STATE atomically. Caller must hold STATE_LOCK."""
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(STATE, fh, indent=2)
    os.replace(tmp, STATE_PATH)


def _load_state() -> None:
    """Load STATE from disk and rebuild the processing queue from status."""
    global QUEUE, PROCESSING
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        STATE["documents"] = data.get("documents", {})
        STATE["clients"] = data.get("clients", {})
        STATE["seq_doc"] = data.get("seq_doc", 0)
        STATE["seq_client"] = data.get("seq_client", 0)
    # Any document still "pending" was never finished -> re-enqueue.
    QUEUE = [
        doc_id
        for doc_id, doc in STATE["documents"].items()
        if doc.get("status") == "pending"
    ]
    PROCESSING = None
    if QUEUE:
        WAKE.set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _next_doc_id() -> str:
    STATE["seq_doc"] += 1
    return f"doc_{STATE['seq_doc']:03d}"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return slug or "client"


def _next_client_id(name: str) -> str:
    base = "client_" + _slugify(name)
    cid = base
    n = 2
    while cid in STATE["clients"]:
        cid = f"{base}_{n}"
        n += 1
    return cid


def _abs_image_path(doc: dict) -> str:
    ip = doc.get("image_path")
    if not ip:
        return ""
    return ip if os.path.isabs(ip) else os.path.join(BASE_DIR, ip)


def _wrap_fields(plain: dict, retried: bool = False) -> dict:
    """Turn {key: value_str} into the stored {key: {value, corrected}} shape.

    Adds "low_confidence": true only when a deterministic signal fires
    (docs/API.md) — never a fake probability, and only present when true.
    """
    out = {}
    for k, v in plain.items():
        field = {"value": v, "corrected": False}
        if pipeline.field_low_confidence(k, v, retried):
            field["low_confidence"] = True
        out[k] = field
    return out


# ---------------------------------------------------------------------------
# Background worker — sequential, one document at a time.
# ---------------------------------------------------------------------------
def _worker_loop() -> None:
    global PROCESSING
    while True:
        WAKE.wait(timeout=1.0)
        with STATE_LOCK:
            if not QUEUE:
                WAKE.clear()
                doc_id = None
            else:
                doc_id = QUEUE.pop(0)
                PROCESSING = doc_id
                doc = STATE["documents"].get(doc_id)
                img_path = _abs_image_path(doc) if doc else ""
        if doc_id is None:
            continue

        result = None
        error = None
        t0 = time.time()
        try:
            with open(img_path, "rb") as fh:
                img_b64 = base64.b64encode(fh.read()).decode()
            result = pipeline.run_pipeline(img_b64)
        except Exception as exc:  # noqa: BLE001 - never let the worker die
            error = str(exc)
        latency = round(time.time() - t0, 2)

        low_conf_count = 0
        with STATE_LOCK:
            doc = STATE["documents"].get(doc_id)
            if doc is not None:
                if result is None:
                    doc["status"] = "unrecognized"
                    doc["doc_type"] = pipeline.UNRECOGNIZED
                    doc["fields"] = {}
                    doc["error"] = error
                else:
                    doc["status"] = result["status"]
                    doc["doc_type"] = result["doc_type"]
                    doc["fields"] = _wrap_fields(result["fields"], result.get("retried"))
                    doc.pop("error", None)
                low_conf_count = sum(
                    1 for f in doc["fields"].values() if f.get("low_confidence")
                )
            PROCESSING = None
            _persist_locked()

        # Event log (append-only; drives /stats/timeline).
        if doc is not None:
            retried = bool(result.get("retried")) if result else False
            fields_total = len(result["fields"]) if result else 0
            ev_type = doc["status"] if doc["status"] in ("extracted", "unrecognized") else "extracted"
            _append_event({
                "type": ev_type,
                "doc_id": doc_id,
                "doc_type": doc["doc_type"],
                "latency_s": latency,
                "fields_total": fields_total,
                "fields_low_confidence": low_conf_count,
                "retried": retried,
            })


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="KeepBook", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    with STATE_LOCK:
        _load_state()
    t = threading.Thread(target=_worker_loop, name="keepbook-worker", daemon=True)
    t.start()


# ---------------------------- Intake ---------------------------------------
async def _save_bytes(data: bytes, orig_name: str) -> dict:
    """Create a pending Document from raw image bytes. Caller holds lock."""
    ext = os.path.splitext(orig_name or "")[1].lower()
    if ext not in IMAGE_EXTS:
        ext = ".png"
    doc_id = _next_doc_id()
    rel_path = os.path.join("uploads", f"{doc_id}{ext}")
    with open(os.path.join(BASE_DIR, rel_path), "wb") as fh:
        fh.write(data)
    doc = {
        "id": doc_id,
        "client_id": None,
        "status": "pending",
        "doc_type": None,
        "image_path": rel_path,
        "received_at": _now_iso(),
        "fields": {},
        "source_name": orig_name or None,
    }
    STATE["documents"][doc_id] = doc
    QUEUE.append(doc_id)
    return doc


@app.post("/intake")
async def intake(request: Request):
    ct = request.headers.get("content-type", "")
    queued = []

    if ct.startswith("application/json"):
        body = await request.json()
        folder = body.get("folder")
        if not folder or not os.path.isdir(folder):
            raise HTTPException(400, f"folder not found: {folder!r}")
        names = sorted(
            n
            for n in os.listdir(folder)
            if os.path.splitext(n)[1].lower() in IMAGE_EXTS
        )
        if not names:
            raise HTTPException(400, f"no images in folder: {folder!r}")
        with STATE_LOCK:
            for n in names:
                with open(os.path.join(folder, n), "rb") as fh:
                    data = fh.read()
                doc = await _save_bytes(data, n)
                queued.append(doc["id"])
            _persist_locked()
    else:
        form = await request.form()
        uploads = [v for v in form.values() if isinstance(v, StarletteUploadFile)]
        if not uploads:
            raise HTTPException(400, "no files in multipart body")
        with STATE_LOCK:
            for up in uploads:
                data = await up.read()
                doc = await _save_bytes(data, up.filename)
                queued.append(doc["id"])
            _persist_locked()

    WAKE.set()
    return {"queued": queued}


# ----------------------------- Queue ---------------------------------------
@app.get("/queue")
async def get_queue():
    with STATE_LOCK:
        pending = len(QUEUE)
        processing = PROCESSING
        done = sum(
            1
            for d in STATE["documents"].values()
            if d.get("status") in ("extracted", "unrecognized", "confirmed")
        )
    return {"pending": pending, "processing": processing, "done": done}


# --------------------------- Documents -------------------------------------
@app.get("/documents")
async def get_documents():
    with STATE_LOCK:
        return list(STATE["documents"].values())


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    with STATE_LOCK:
        doc = STATE["documents"].get(doc_id)
        if doc is None:
            raise HTTPException(404, f"no document {doc_id}")
        return doc


@app.get("/documents/{doc_id}/image")
async def get_document_image(doc_id: str):
    with STATE_LOCK:
        doc = STATE["documents"].get(doc_id)
        if doc is None:
            raise HTTPException(404, f"no document {doc_id}")
        path = _abs_image_path(doc)
    if not path or not os.path.exists(path):
        raise HTTPException(404, f"no image for {doc_id}")
    return FileResponse(path)


@app.post("/documents/{doc_id}/confirm")
async def confirm_document(doc_id: str, request: Request):
    body = await request.json()
    incoming = body.get("fields", {}) or {}
    with STATE_LOCK:
        doc = STATE["documents"].get(doc_id)
        if doc is None:
            raise HTTPException(404, f"no document {doc_id}")

        old_type = doc.get("doc_type")
        manual_type_change = bool(body.get("doc_type")) and body["doc_type"] != old_type
        if body.get("doc_type"):
            doc["doc_type"] = body["doc_type"]
        if body.get("client_id") is not None:
            doc["client_id"] = body["client_id"]

        fields = doc.get("fields", {})
        corrected_keys = []
        for key, raw_val in incoming.items():
            new_val = "" if raw_val is None else str(raw_val)
            cur = fields.get(key, {"value": "", "corrected": False})
            baseline = cur.get("original_value") if cur.get("corrected") else cur.get("value", "")
            if new_val != str(cur.get("value", "")):
                fields[key] = {
                    "value": new_val,
                    "corrected": True,
                    "original_value": baseline,
                }
                # A field the reviewer corrected is no longer low-confidence.
                fields[key].pop("low_confidence", None)
                corrected_keys.append(key)
        doc["fields"] = fields
        doc["status"] = "confirmed"

        # Checklist: a confirmed doc_type joins the client's received_docs.
        client = STATE["clients"].get(doc.get("client_id"))
        if client is not None:
            dt = doc.get("doc_type")
            if dt and dt != pipeline.UNRECOGNIZED and dt not in client["received_docs"]:
                client["received_docs"].append(dt)

        _persist_locked()
        final = json.loads(json.dumps(doc))  # snapshot for use outside the lock

    _append_event({
        "type": "confirmed",
        "doc_id": doc_id,
        "doc_type": final.get("doc_type"),
        "fields_corrected": len(corrected_keys),
        "corrected_keys": corrected_keys,
        "manual_type_change": manual_type_change,
    })
    return final


# ---------------------------- Clients --------------------------------------
@app.get("/clients")
async def get_clients():
    with STATE_LOCK:
        return list(STATE["clients"].values())


@app.post("/clients")
async def create_client(request: Request):
    body = await request.json()
    name = body.get("name")
    if not name:
        raise HTTPException(400, "client name required")
    expected = body.get("expected_docs", []) or []
    with STATE_LOCK:
        cid = _next_client_id(name)
        client = {
            "id": cid,
            "name": name,
            "expected_docs": list(expected),
            "received_docs": [],
        }
        STATE["clients"][cid] = client
        STATE["seq_client"] += 1
        _persist_locked()
        return client


# ----------------------------- Stats ---------------------------------------
@app.get("/stats")
async def get_stats():
    with STATE_LOCK:
        extracted = 0
        corrected = 0
        for d in STATE["documents"].values():
            if d.get("status") == "unrecognized":
                continue
            for f in (d.get("fields") or {}).values():
                extracted += 1
                if f.get("corrected"):
                    corrected += 1
    rate = round(corrected / extracted, 4) if extracted else 0
    return {
        "fields_extracted": extracted,
        "fields_corrected": corrected,
        "correction_rate": rate,
    }


# ---------------------- Timeline (stretch: Stats for Nerds) ----------------
def _read_events():
    if not os.path.exists(EVENTS_PATH):
        return []
    events = []
    with EVENTS_LOCK:
        with open(EVENTS_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    return events


def _parse_ts(ts: str):
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


@app.get("/stats/timeline")
async def stats_timeline(hours: int = 24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    events = []
    for e in _read_events():
        dt = _parse_ts(e.get("ts", ""))
        if dt is not None and dt >= cutoff:
            e["_dt"] = dt
            events.append(e)

    processed = [e for e in events if e.get("type") in ("extracted", "unrecognized")]
    confirms = [e for e in events if e.get("type") == "confirmed"]

    # Hourly buckets (oldest first), only for hours with activity.
    buckets = {}
    for e in processed:
        key = e["_dt"].strftime("%Y-%m-%dT%H")
        buckets.setdefault(key, {"docs": 0, "corrections": 0})["docs"] += 1
    for e in confirms:
        key = e["_dt"].strftime("%Y-%m-%dT%H")
        buckets.setdefault(key, {"docs": 0, "corrections": 0})["corrections"] += int(
            e.get("fields_corrected", 0)
        )
    bucket_list = [
        {"hour": k[11:13] + ":00", "docs": v["docs"], "corrections": v["corrections"]}
        for k, v in sorted(buckets.items())
    ]

    docs_processed = len(processed)
    fields_extracted = sum(int(e.get("fields_total", 0)) for e in processed)
    fields_low_confidence = sum(int(e.get("fields_low_confidence", 0)) for e in processed)
    fields_corrected = sum(int(e.get("fields_corrected", 0)) for e in confirms)
    manual_changes = sum(1 for e in confirms if e.get("manual_type_change"))
    latencies = sorted(
        float(e["latency_s"]) for e in processed if e.get("latency_s") is not None
    )

    if latencies:
        mid = len(latencies) // 2
        median_lat = (
            latencies[mid]
            if len(latencies) % 2
            else (latencies[mid - 1] + latencies[mid]) / 2
        )
    else:
        median_lat = 0

    by_cat = {}
    for e in confirms:
        for key in e.get("corrected_keys", []) or []:
            cat = pipeline.correction_category(key)
            by_cat[cat] = by_cat.get(cat, 0) + 1
        if e.get("manual_type_change"):
            by_cat["doc_type"] = by_cat.get("doc_type", 0) + 1

    totals = {
        "docs_processed": docs_processed,
        "fields_extracted": fields_extracted,
        "fields_low_confidence": fields_low_confidence,
        "fields_corrected": fields_corrected,
        "correction_rate": round(fields_corrected / fields_extracted, 4)
        if fields_extracted
        else 0,
        "first_try_type_acc": round((len(confirms) - manual_changes) / len(confirms), 4)
        if confirms
        else 0,
        "median_latency_s": round(median_lat, 2),
        "corrections_by_category": by_cat,
    }
    return {"hours": hours, "buckets": bucket_list, "totals": totals}


# --------------------- Static frontend (mount LAST) ------------------------
# API routes above win; the SPA + assets are served from "/" for everything else.
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/")
    async def _root():
        return JSONResponse({"service": "KeepBook", "frontend": "not found"})
