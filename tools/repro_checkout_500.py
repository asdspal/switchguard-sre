import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from demo_app.main import app
from demo_app.db import init_db, get_db


def execute_repro_probe(incident_id: str = "") -> dict:
    init_db()
    client = TestClient(app)
    synthetic_payload = {
        "customer_email": "synth-user-89a@example.invalid",
        "card_number": "4111111111111111",
        "amount_cents": 4999,
        "discount_code": "SWITCH20",
    }
    response = client.post("/api/v1/checkout", json=synthetic_payload)
    body = response.json()

    target_inc_id = incident_id or os.getenv("SWITCHGUARD_INCIDENT_ID", "")
    if not target_inc_id:
        with get_db() as conn:
            latest = conn.execute(
                "SELECT incident_id FROM incidents ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if latest:
                target_inc_id = latest["incident_id"]

    if target_inc_id and response.status_code == 500:
        agent_key = os.getenv("SWITCHGUARD_AGENT_KEY", "sg_agent_dev_key_2026")
        client.post(
            f"/api/v1/incidents/{target_inc_id}/repro",
            headers={"X-Agent-Key": agent_key},
            json={
                "repro_exit_code": 1,
                "repro_traceback": body.get("exception", "HTTP 500 Internal Server Error"),
                "suspect_commit": body.get("version", "v2.14.0"),
            },
        )

    return {"status_code": response.status_code, "body": body, "incident_id": target_inc_id}


def test_checkout_with_synthetic_luhn_fixture():
    """Executed by @sre-repro in #incident-war-room to prove or verify the v2.14.0 checkout bug."""
    res = execute_repro_probe()
    assert res["status_code"] == 200, (
        f"REPRODUCED HTTP {res['status_code']} REGRESSION in {res['body'].get('version')}: "
        f"{res['body'].get('exception')}"
    )
