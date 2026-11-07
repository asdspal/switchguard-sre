import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from demo_app.main import app
from demo_app.db import init_db

ROOT_DIR = Path(__file__).resolve().parent.parent
AGENT_HEADERS = {"X-Agent-Key": "sg_agent_dev_key_2026"}
ADMIN_HEADERS = {"X-Admin-Token": "sg_admin_rollback_secret_2026"}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_api.db")
    monkeypatch.setenv("SWITCHGUARD_DB_PATH", db_file)
    init_db(db_file)
    yield db_file


def test_checkout_fails_500_on_v214_with_discount():
    client = TestClient(app)
    res = client.post(
        "/api/v1/checkout",
        json={
            "customer_email": "synth-user-89a@example.invalid",
            "card_number": "4111111111111111",
            "amount_cents": 4999,
            "discount_code": "SWITCH20",
        },
    )
    assert res.status_code == 500
    assert "KeyError" in res.json()["exception"]


def test_airlock_requires_agent_key():
    client = TestClient(app)
    res = client.post(
        "/api/v1/airlock/scrub",
        headers={"Idempotency-Key": "k1"},
        json={"external_ticket_ref": "SUP-1", "raw_report_text": "test"},
    )
    assert res.status_code == 401


def test_tampered_flashprove_returns_422_and_blocks_rollback():
    client = TestClient(app)
    scrub = client.post(
        "/api/v1/airlock/scrub",
        headers={**AGENT_HEADERS, "Idempotency-Key": "idem-t1"},
        json={"external_ticket_ref": "SUP-T1", "raw_report_text": "Crash for bob@acme.io"},
    ).json()

    tampered = json.loads((ROOT_DIR / "fixtures" / "flashprove" / "tampered_model.json").read_text())
    fp_res = client.post(
        "/api/v1/flashprove/verify",
        headers=AGENT_HEADERS,
        json={
            "incident_id": scrub["incident_id"],
            **tampered,
        },
    )
    assert fp_res.status_code == 422
    att_id = fp_res.json()["attestation_id"]

    rb_res = client.post(
        "/api/v1/admin/rollback",
        headers={**ADMIN_HEADERS, "Idempotency-Key": "rb-t1"},
        json={
            "incident_id": scrub["incident_id"],
            "attestation_id": att_id,
            "target_version": "v2.13.2",
            "approved_by_human": "@priya",
            "approval_chat_message": "@-release-commander Approved. Roll back to v2.13.2",
        },
    )
    assert rb_res.status_code == 403


def test_rollback_rejected_without_exact_human_approval_phrase():
    client = TestClient(app)
    scrub = client.post(
        "/api/v1/airlock/scrub",
        headers={**AGENT_HEADERS, "Idempotency-Key": "idem-u1"},
        json={"external_ticket_ref": "SUP-U1", "raw_report_text": "Crash"},
    ).json()
    valid = json.loads((ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json").read_text())
    fp_res = client.post(
        "/api/v1/flashprove/verify",
        headers=AGENT_HEADERS,
        json={"incident_id": scrub["incident_id"], **valid},
    ).json()

    rb_res = client.post(
        "/api/v1/admin/rollback",
        headers={**ADMIN_HEADERS, "Idempotency-Key": "rb-u1"},
        json={
            "incident_id": scrub["incident_id"],
            "attestation_id": fp_res["attestation_id"],
            "target_version": "v2.13.2",
            "approved_by_human": "@priya",
            "approval_chat_message": "Looks fine go ahead",
        },
    )
    assert rb_res.status_code == 403


def test_full_api_remediation_lifecycle():
    client = TestClient(app)
    # 1. Scrub
    scrub = client.post(
        "/api/v1/airlock/scrub",
        headers={**AGENT_HEADERS, "Idempotency-Key": "idem-ok1"},
        json={
            "external_ticket_ref": "SUP-9042",
            "raw_report_text": "Customer alice@acme.io card 4532015112830366 failed on SWITCH20",
        },
    ).json()
    inc_id = scrub["incident_id"]

    # 2. Record Repro
    repro = client.post(
        f"/api/v1/incidents/{inc_id}/repro",
        headers=AGENT_HEADERS,
        json={"repro_exit_code": 1, "repro_traceback": "KeyError: discount_rate", "suspect_commit": "v2.14.0"},
    )
    assert repro.status_code == 200

    # 3. Verify FlashProve
    valid = json.loads((ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json").read_text())
    fp_res = client.post(
        "/api/v1/flashprove/verify",
        headers=AGENT_HEADERS,
        json={"incident_id": inc_id, **valid},
    )
    assert fp_res.status_code == 200
    att_id = fp_res.json()["attestation_id"]

    # 4. Human-Approved Rollback
    rb_res = client.post(
        "/api/v1/admin/rollback",
        headers={**ADMIN_HEADERS, "Idempotency-Key": "rb-ok1"},
        json={
            "incident_id": inc_id,
            "attestation_id": att_id,
            "target_version": "v2.13.2",
            "approved_by_human": "@priya-sre",
            "approval_chat_message": "@-release-commander Approved. Roll back to v2.13.2",
        },
    )
    assert rb_res.status_code == 200
    assert rb_res.json()["active_version"] == "v2.13.2"

    # 5. Checkout now returns 200 OK
    chk = client.post("/api/v1/checkout", json=scrub["synthetic_fixture"])
    assert chk.status_code == 200
    assert chk.json()["version"] == "v2.13.2"


def test_list_incidents_summary():
    client = TestClient(app)
    res = client.get("/api/v1/incidents")
    assert res.status_code == 200
    assert "service_state" in res.json()
    assert "totals" in res.json()
