import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx
from demo_app.db import init_db
from demo_app.airlock import persist_airlock_scrub


def run_airlock_cli(ticket_ref: str, raw_text: str, idempotency_key: str = "") -> dict:
    idem = idempotency_key or hashlib.sha256(f"{ticket_ref}:{raw_text}".encode("utf-8")).hexdigest()[:32]
    api_url = os.getenv("SWITCHGUARD_API_URL", f"http://localhost:{os.getenv('SWITCHGUARD_PORT', '8090')}")
    agent_key = os.getenv("SWITCHGUARD_AGENT_KEY", "sg_agent_dev_key_2026")

    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.post(
                f"{api_url}/api/v1/airlock/scrub",
                headers={"X-Agent-Key": agent_key, "Idempotency-Key": idem},
                json={"external_ticket_ref": ticket_ref, "raw_report_text": raw_text},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    init_db()
    return persist_airlock_scrub(
        external_ticket_ref=ticket_ref,
        raw_report_text=raw_text,
        idempotency_key=idem,
    )


def main():
    parser = argparse.ArgumentParser(description="SwitchGuard SRE Tier-1 PII Airlock Scrubber")
    parser.add_argument("--ticket-ref", required=True, help="Support ticket reference (e.g. SUP-9042)")
    parser.add_argument("--raw-text", required=True, help="Raw customer crash report text")
    parser.add_argument("--idempotency-key", default="", help="Optional idempotency key")
    args = parser.parse_args()

    result = run_airlock_cli(args.ticket_ref, args.raw_text, args.idempotency_key)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
