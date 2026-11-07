import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from demo_app.main import app
from demo_app.db import init_db, get_db


def run_flashprove_cli(incident_id: str, bundle_path: str) -> dict:
    init_db()
    if not incident_id:
        with get_db() as conn:
            row = conn.execute("SELECT incident_id FROM incidents ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:
                raise RuntimeError("No active incident found in database")
            incident_id = row["incident_id"]

    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    agent_key = os.getenv("SWITCHGUARD_AGENT_KEY", "sg_agent_dev_key_2026")
    client = TestClient(app)
    resp = client.post(
        "/api/v1/flashprove/verify",
        headers={"X-Agent-Key": agent_key},
        json={
            "incident_id": incident_id,
            "model_name": bundle["model_name"],
            "weight_commitment_hash": bundle["weight_commitment_hash"],
            "proof_sha256": bundle["proof_sha256"],
            "token_count": bundle["token_count"],
            "diagnostic_claim": bundle.get("diagnostic_claim"),
            "simulated_verify_duration_ms": bundle.get("simulated_verify_duration_ms"),
        },
    )
    data = resp.json()
    data["http_status"] = resp.status_code
    return data


def main():
    parser = argparse.ArgumentParser(description="SwitchGuard SRE Anthropic FlashProve CPU Verifier")
    parser.add_argument("--incident-id", default="", help="Incident ID (defaults to latest)")
    parser.add_argument(
        "--bundle",
        default=str(ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json"),
        help="Path to FlashProve proof JSON bundle",
    )
    args = parser.parse_args()

    result = run_flashprove_cli(args.incident_id, args.bundle)
    print(json.dumps(result, indent=2))
    if not result.get("is_verified"):
        sys.exit(2)


if __name__ == "__main__":
    main()
