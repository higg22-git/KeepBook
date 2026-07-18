"""T65 — classify-only doc types (extract: false).

A classify-only type is classified + client-assigned + human-confirmed, with
ZERO field extraction. Two invariants are pinned here:

  1. When the classifier returns a classify-only type, the pipeline makes
     EXACTLY ONE model call (classify only, no extraction). With no extracted
     values the silent-wrong failure class cannot exist for these docs.
  2. The bigger enum does NOT erode UNRECOGNIZED discipline: junk still lands
     UNRECOGNIZED after the same one-retry path.

All model access is faked (no Ollama/GPU). The pipeline-level tests assert the
call count directly; the API-level test drives intake -> confirm -> checklist.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00"
    b"\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _import_pipeline():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    try:
        return importlib.import_module("pipeline")
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
        pytest.skip(f"backend pipeline is not available yet: {exc}")


# --------------------------------------------------------------------------- #
# Pipeline-level: the "exactly one model call" money assertion.
# --------------------------------------------------------------------------- #
def test_classify_only_type_skips_extraction_entirely(monkeypatch):
    pipeline = _import_pipeline()
    monkeypatch.setenv("PREPROCESS", "0")  # hermetic: no cv2 / image work
    calls = []

    def fake(_image_b64, prompt, model=None):
        calls.append(prompt)
        return json.dumps({"doc_type": "1099-DIV", "handwritten": False})

    monkeypatch.setattr(pipeline, "model_extract", fake)
    result = pipeline.run_pipeline("Zm9v")  # b64("foo")

    assert result["status"] == "extracted"
    assert result["doc_type"] == "1099-DIV"
    assert result["fields"] == {}
    assert result.get("classify_only") is True
    # The whole point: one call (classify), never an extraction call.
    assert len(calls) == 1
    assert all("classifier" in p for p in calls)


def test_classify_only_bigger_enum_keeps_unrecognized_discipline(monkeypatch):
    pipeline = _import_pipeline()
    monkeypatch.setenv("PREPROCESS", "0")
    calls = []

    def junk(_image_b64, prompt, model=None):
        calls.append(prompt)
        return "this is not JSON"

    monkeypatch.setattr(pipeline, "model_extract", junk)
    result = pipeline.run_pipeline("Zm9v")

    assert result["status"] == "unrecognized"
    assert result["doc_type"] == "UNRECOGNIZED"
    assert result["fields"] == {}
    # classify + one retry, then give up — unchanged by the larger enum.
    assert len(calls) == 2


def test_normalize_maps_new_classify_only_types_and_still_rejects_junk():
    pipeline = _import_pipeline()
    mapped = {
        "1099-DIV": "1099-DIV",
        "Form 1099-DIV Dividends and Distributions": "1099-DIV",
        "1099-B": "1099-B",
        "1099-R": "1099-R",
        "1099-G": "1099-G",
        "1098-T": "1098-T",
        "1098-E Student Loan Interest": "1098-E",
        "Form 1095-A": "1095-A",
        "W-9": "W-9",
        "property tax statement": "property tax statement",
        "charitable donation receipt": "charitable receipt",
        "brokerage statement": "brokerage statement",
        "Consolidated 1099 Statement": "brokerage statement",
        "engagement letter": "engagement letter",
    }
    for raw, expected in mapped.items():
        assert pipeline.normalize_doc_type(raw) == expected, raw

    # The 6 extraction types + UNRECOGNIZED must be untouched by the new branches.
    assert pipeline.normalize_doc_type("W-2") == "W-2"
    assert pipeline.normalize_doc_type("1099-NEC") == "1099-NEC"
    assert pipeline.normalize_doc_type("1098") == "1098"  # bare 1098 stays mortgage
    assert pipeline.normalize_doc_type("K-1") == "K-1"
    assert pipeline.normalize_doc_type("UNRECOGNIZED") == "UNRECOGNIZED"
    # Force-fit guard: a plain receipt / letter must NOT become a classify-only
    # type just because the enum now contains "charitable receipt"/"engagement
    # letter".
    assert pipeline.normalize_doc_type("a grocery store receipt") == "UNRECOGNIZED"
    assert pipeline.normalize_doc_type("a lease renewal letter") == "UNRECOGNIZED"


def test_classify_only_types_have_no_field_schema_entry():
    pipeline = _import_pipeline()
    for t in pipeline.CLASSIFY_ONLY_TYPES:
        assert t not in pipeline.FIELD_SCHEMA, t
    # And they are advertised to the classifier (enum grows, escape hatch stays).
    prompt = pipeline.build_classify_prompt()
    for t in pipeline.CLASSIFY_ONLY_TYPES:
        assert f'"{t}"' in prompt, t
    assert pipeline.UNRECOGNIZED in prompt


# --------------------------------------------------------------------------- #
# API-level: intake -> confirm -> a checklist item is satisfied.
# --------------------------------------------------------------------------- #
def _import_backend():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    try:
        return importlib.import_module("main")
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
        pytest.skip(f"backend API module is not available yet: {exc}")


@pytest.fixture()
def api(tmp_path):
    try:
        from fastapi.testclient import TestClient
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
        pytest.skip(f"FastAPI TestClient dependencies are not installed: {exc}")

    module = _import_backend()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    module.BASE_DIR = str(tmp_path)
    module.UPLOADS_DIR = str(uploads)
    module.STATE_PATH = str(tmp_path / "state.json")
    module.EVENTS_PATH = str(tmp_path / "events.jsonl")
    with module.STATE_LOCK:
        module.STATE.clear()
        module.STATE.update(
            {"documents": {}, "clients": {}, "seq_doc": 0, "seq_client": 0}
        )
        module.QUEUE.clear()
        module.PROCESSING = None
        module.WAKE.clear()
    with TestClient(module.app) as client:
        yield module, client


def _patch_adapter(monkeypatch, module, response):
    runtime = importlib.import_module("model_runtime")

    def fake_extract(_image_b64, prompt, **_kwargs):
        return response(prompt) if callable(response) else response

    monkeypatch.setattr(runtime, "extract", fake_extract)
    monkeypatch.setattr(module.pipeline, "model_extract", fake_extract)


def _wait_for_status(client, doc_id, expected, timeout=3.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/documents/{doc_id}").json()
        if last["status"] == expected:
            return last
        time.sleep(0.01)
    pytest.fail(f"{doc_id} never reached {expected}; last={last}")


def test_classify_only_intake_confirm_satisfies_checklist(api, monkeypatch):
    module, client = api
    calls = []

    def classify_only_adapter(prompt):
        calls.append(prompt)
        # If extraction were ever attempted this prompt would NOT be the
        # classifier prompt — fail loudly rather than silently extract.
        assert "classifier" in prompt, "extraction must never run for classify-only"
        return json.dumps({"doc_type": "1099-DIV", "handwritten": False})

    _patch_adapter(monkeypatch, module, classify_only_adapter)

    created = client.post(
        "/clients", json={"name": "Doe, A.", "expected_docs": ["1099-DIV", "W-2"]}
    )
    assert created.status_code == 200
    client_id = created.json()["id"]

    intake = client.post("/intake", files=[("file", ("div.png", PNG, "image/png"))])
    assert intake.status_code == 200
    doc_id = intake.json()["queued"][0]

    doc = _wait_for_status(client, doc_id, "extracted")
    assert doc["doc_type"] == "1099-DIV"
    assert doc["fields"] == {}
    # Exactly one model call reached the adapter: classify, no extraction.
    assert len(calls) == 1

    # Extraction alone does not check the box.
    clients = {c["id"]: c for c in client.get("/clients").json()}
    assert clients[client_id]["received_docs"] == []

    confirmed = client.post(
        f"/documents/{doc_id}/confirm",
        json={"client_id": client_id, "doc_type": "1099-DIV", "fields": {}},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    # The confirmed classify-only doc satisfies the expected "1099-DIV" item.
    clients = {c["id"]: c for c in client.get("/clients").json()}
    assert clients[client_id]["received_docs"] == ["1099-DIV"]
