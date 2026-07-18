"""Contract tests for POST /documents/{id}/unconfirm (re-open a confirmed doc).

Mirrors the fake-adapter fixture pattern of test_delete_document.py. Covers the
confirm -> unconfirm -> re-confirm round trip, count-aware checklist un-check,
correction survival, invalid-status / unknown-id rejections, and persistence.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00"
    b"\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    module = importlib.import_module("main")
    root = tmp_path_factory.mktemp("unconfirm-document")
    uploads = root / "uploads"
    uploads.mkdir()

    module.BASE_DIR = str(root)
    module.UPLOADS_DIR = str(uploads)
    module.STATE_PATH = str(root / "state.json")
    module.EVENTS_PATH = str(root / "events.jsonl")

    with TestClient(module.app) as client:
        yield module, client, root


@pytest.fixture(autouse=True)
def clean_state(api):
    module, _client, root = api
    deadline = time.monotonic() + 2
    while module.PROCESSING is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert module.PROCESSING is None, "previous test left the worker processing"

    with module.STATE_LOCK:
        module.STATE.clear()
        module.STATE.update(
            {"documents": {}, "clients": {}, "seq_doc": 0, "seq_client": 0}
        )
        module.QUEUE.clear()
        module.PROCESSING = None
        module.WAKE.clear()
        module._persist_locked()

    events = root / "events.jsonl"
    if events.exists():
        events.unlink()


@pytest.fixture(autouse=True)
def fake_model_adapter(api, monkeypatch):
    module, _client, _root = api
    runtime = importlib.import_module("model_runtime")

    def fake_extract(_image_b64, prompt, **_kwargs):
        if "classifier" in prompt:
            return json.dumps({"doc_type": "W-2"})
        return json.dumps(
            {
                "employee_name": "Reopen Contract",
                "ssn": "123-45-6789",
                "employer": "KeepBook Test LLC",
                "box1_wages": "100.00",
                "box2_fed_withheld": "10.00",
            }
        )

    monkeypatch.setattr(runtime, "extract", fake_extract)
    monkeypatch.setattr(module.pipeline, "model_extract", fake_extract)


def _create_client(client, name="Reopen Client", expected_docs=None):
    response = client.post(
        "/clients",
        json={"name": name, "expected_docs": expected_docs or ["W-2"]},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _create_extracted_document(client, name="reopen-me.png"):
    response = client.post("/intake", files=[("file", (name, PNG, "image/png"))])
    assert response.status_code == 200
    doc_id = response.json()["queued"][0]

    deadline = time.monotonic() + 3
    last = None
    while time.monotonic() < deadline:
        fetched = client.get(f"/documents/{doc_id}")
        assert fetched.status_code == 200
        last = fetched.json()
        if last["status"] == "extracted":
            return doc_id
        time.sleep(0.01)
    pytest.fail(f"document {doc_id} did not reach extracted; last state: {last}")


def _confirm(client, doc_id, client_id, doc_type="W-2", fields=None):
    response = client.post(
        f"/documents/{doc_id}/confirm",
        json={"client_id": client_id, "doc_type": doc_type, "fields": fields or {}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    return response.json()


def _unconfirm(client, doc_id):
    response = client.post(f"/documents/{doc_id}/unconfirm")
    assert response.status_code == 200, response.text
    return response.json()


def _clients_by_id(client):
    response = client.get("/clients")
    assert response.status_code == 200
    return {item["id"]: item for item in response.json()}


def test_unconfirm_reopens_last_confirmed_doc_and_unchecks_client_item(api):
    _module, client, _root = api
    client_id = _create_client(client)
    doc_id = _create_extracted_document(client)
    _confirm(client, doc_id, client_id)
    assert _clients_by_id(client)[client_id]["received_docs"] == ["W-2"]

    reopened = _unconfirm(client, doc_id)

    assert reopened["status"] == "extracted"
    assert reopened["doc_type"] == "W-2"
    assert reopened["client_id"] == client_id  # identity preserved for one-click re-confirm
    # Checklist un-checked because this was the only confirmed W-2 for the client.
    assert _clients_by_id(client)[client_id]["received_docs"] == []


def test_unconfirm_is_count_aware_keeps_item_while_another_confirmed_remains(api):
    _module, client, _root = api
    client_id = _create_client(client)
    first_id = _create_extracted_document(client, "first-w2.png")
    second_id = _create_extracted_document(client, "second-w2.png")
    _confirm(client, first_id, client_id)
    _confirm(client, second_id, client_id)
    assert _clients_by_id(client)[client_id]["received_docs"] == ["W-2"]

    _unconfirm(client, first_id)

    # A second confirmed W-2 remains, so the checklist item stays checked.
    assert _clients_by_id(client)[client_id]["received_docs"] == ["W-2"]
    assert client.get(f"/documents/{first_id}").json()["status"] == "extracted"
    assert client.get(f"/documents/{second_id}").json()["status"] == "confirmed"

    # Un-confirming the last one now clears the item.
    _unconfirm(client, second_id)
    assert _clients_by_id(client)[client_id]["received_docs"] == []


def test_reconfirm_after_unconfirm_restores_checklist(api):
    _module, client, _root = api
    client_id = _create_client(client)
    doc_id = _create_extracted_document(client)
    _confirm(client, doc_id, client_id)
    _unconfirm(client, doc_id)
    assert _clients_by_id(client)[client_id]["received_docs"] == []

    # One-click re-confirm: no fields needed, doc_type already on the doc.
    re = client.post(
        f"/documents/{doc_id}/confirm",
        json={"client_id": client_id, "fields": {}},
    )
    assert re.status_code == 200
    assert re.json()["status"] == "confirmed"
    assert _clients_by_id(client)[client_id]["received_docs"] == ["W-2"]


def test_corrections_survive_unconfirm_reconfirm_round_trip(api):
    _module, client, _root = api
    client_id = _create_client(client)
    doc_id = _create_extracted_document(client)

    # Confirm with a correction to box1_wages.
    confirmed = _confirm(
        client, doc_id, client_id, fields={"box1_wages": "250.00"}
    )
    wages = confirmed["fields"]["box1_wages"]
    assert wages["corrected"] is True
    assert wages["value"] == "250.00"
    assert wages["original_value"] == "100.00"

    reopened = _unconfirm(client, doc_id)

    # Correction is preserved verbatim in the reopened (extracted) doc.
    rw = reopened["fields"]["box1_wages"]
    assert rw["corrected"] is True
    assert rw["value"] == "250.00"
    assert rw["original_value"] == "100.00"

    # Re-confirm with no changes: correction still intact, not double-wrapped.
    re = client.post(
        f"/documents/{doc_id}/confirm",
        json={"client_id": client_id, "fields": {}},
    )
    assert re.status_code == 200
    rw2 = re.json()["fields"]["box1_wages"]
    assert rw2["corrected"] is True
    assert rw2["value"] == "250.00"
    assert rw2["original_value"] == "100.00"


def test_unconfirm_non_confirmed_document_is_rejected(api):
    _module, client, _root = api
    _create_client(client)
    doc_id = _create_extracted_document(client)  # still "extracted", never confirmed

    response = client.post(f"/documents/{doc_id}/unconfirm")

    assert response.status_code == 409
    assert client.get(f"/documents/{doc_id}").json()["status"] == "extracted"


def test_unconfirm_nonexistent_document_returns_404(api):
    _module, client, _root = api

    response = client.post("/documents/does-not-exist/unconfirm")

    assert response.status_code == 404


def test_unconfirm_appends_event_and_persists_across_restart(api):
    module, client, root = api
    client_id = _create_client(client)
    doc_id = _create_extracted_document(client)
    _confirm(client, doc_id, client_id)

    _unconfirm(client, doc_id)

    event_rows = [
        json.loads(line)
        for line in (root / "events.jsonl").read_text().splitlines()
        if line
    ]
    assert any(
        e.get("type") == "unconfirmed" and e.get("doc_id") == doc_id
        for e in event_rows
    )

    # Persisted to disk with the reopened status + preserved fields (simulated
    # restart: read state.json straight off disk).
    persisted = json.loads(Path(module.STATE_PATH).read_text())
    pdoc = persisted["documents"][doc_id]
    assert pdoc["status"] == "extracted"
    assert pdoc["doc_type"] == "W-2"
    assert pdoc["client_id"] == client_id
    assert "employee_name" in pdoc["fields"]
    # Checklist un-check also persisted.
    assert persisted["clients"][client_id]["received_docs"] == []
