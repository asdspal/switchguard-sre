import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from demo_app.main import app
from demo_app.db import init_db, update_service_version
from tools.airlock_scrub import run_airlock_cli
from tools.repro_checkout_500 import execute_repro_probe
from tools.flashprove_verify import run_flashprove_cli
from tools.rollback_release import run_rollback_cli

SAMPLE_RAW_TICKET = (
    "[Ticket SUP-9042] URGENT: Customer alice.smith@acme.io (Card: 4532-0151-1283-0366, "
    "Auth: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.sig) hit HTTP 500 Internal Server Error "
    "(KeyError: 'discount_rate') on POST /api/v1/checkout with promo code SWITCH20!"
)


def simulate_outage(run_pipeline: bool = False) -> dict:
    init_db()
    update_service_version("v2.14.0", True)
    client = TestClient(app)

    crash_resp = client.post(
        "/api/v1/checkout",
        json={
            "customer_email": "alice.smith@acme.io",
            "card_number": "4532015112830366",
            "amount_cents": 4999,
            "discount_code": "SWITCH20",
        },
    )

    print("=" * 78)
    print("1. SIMULATED PRODUCTION CRASH ON cart-service (v2.14.0)")
    print(f"   HTTP Status: {crash_resp.status_code} | Response: {crash_resp.json()}")
    print("\n2. PASTE THIS RAW TICKET INTO SWITCH ROOM 1 (#alerts-intake):")
    print("-" * 78)
    print(SAMPLE_RAW_TICKET)
    print("-" * 78)

    result = {"crash_status": crash_resp.status_code, "raw_ticket": SAMPLE_RAW_TICKET}

    if run_pipeline:
        print("\n3. RUNNING AUTOMATED PIPELINE WALKTHROUGH...")
        scrub = run_airlock_cli("SUP-9042", SAMPLE_RAW_TICKET)
        print(f"   [Room 1 @airlock-triager] Scrubbed PII -> Incident: {scrub['incident_id']}")

        repro = execute_repro_probe(scrub["incident_id"])
        print(f"   [Room 2 @sre-repro] Reproduced HTTP {repro['status_code']} crash with synthetic Luhn card")

        valid_bundle = str(ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json")
        fp = run_flashprove_cli(scrub["incident_id"], valid_bundle)
        print(
            f"   [Room 2 @release-commander] FlashProve Verified: {fp['is_verified']} "
            f"(Attestation: {fp['attestation_id']}, Soundness: {fp['soundness_bound']})"
        )

        rb = run_rollback_cli(
            incident_id=scrub["incident_id"],
            attestation_id=fp["attestation_id"],
            approved_by="@priya-sre",
            approval_msg="@release-commander Approved. Roll back to v2.13.2",
        )
        print(
            f"   [Human Sign-Off -> Rollback] Restored to {rb['health']['active_version']} "
            f"(Post-Rollback Checkout HTTP {rb['post_rollback_checkout_status']})"
        )
        print(f"   [Room Document] Wrote Postmortem to: {rb['postmortem_file']}")
        result["pipeline"] = rb

    print("=" * 78)
    return result


def main():
    parser = argparse.ArgumentParser(description="SwitchGuard SRE Outage Simulator")
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Execute the full Airlock -> Repro -> FlashProve -> Rollback pipeline locally",
    )
    args = parser.parse_args()
    simulate_outage(run_pipeline=args.run_pipeline)


if __name__ == "__main__":
    main()
