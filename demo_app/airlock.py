import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from demo_app.db import get_db

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SECRET_RE = re.compile(
    r"(?:Bearer\s+[A-Za-z0-9\-._~+/]+=*|eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+|sk-[A-Za-z0-9]{16,})",
    re.IGNORECASE,
)
INJECTION_RE = re.compile(
    r"(ignore\s+(?:all\s+)?previous\s+instructions|system\s+prompt|drop\s+table|rm\s+-rf\s+/|"
    r"you\s+are\s+now\s+in\s+developer\s+mode)",
    re.IGNORECASE,
)
PROMO_RE = re.compile(r"\b(SWITCH20|SAVE50|VIP10)\b")


def luhn_is_valid(card_number: str) -> bool:
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    odd_sum = sum(digits[-1::-2])
    even_sum = sum(sum(divmod(2 * d, 10)) for d in digits[-2::-2])
    return (odd_sum + even_sum) % 10 == 0


def scrub_text(raw_text: str) -> Dict[str, Any]:
    secrets = SECRET_RE.findall(raw_text)
    sanitized = SECRET_RE.sub("[SECRET_REDACTED]", raw_text)

    cards = CARD_RE.findall(sanitized)
    sanitized = CARD_RE.sub("[CARD_REDACTED]", sanitized)

    ssns = SSN_RE.findall(sanitized)
    sanitized = SSN_RE.sub("[SSN_REDACTED]", sanitized)

    emails = EMAIL_RE.findall(sanitized)
    sanitized = EMAIL_RE.sub("[EMAIL_REDACTED]", sanitized)

    injections = INJECTION_RE.findall(sanitized)
    sanitized = INJECTION_RE.sub("[PROMPT_INJECTION_BLOCKED]", sanitized)

    promo_match = PROMO_RE.search(raw_text)
    discount_code = promo_match.group(1) if promo_match else "SWITCH20"

    synth_card = "4111111111111111"
    assert luhn_is_valid(synth_card), "Synthetic card must be Luhn-valid"

    synthetic_fixture = {
        "customer_email": "synth-user-89a@example.invalid",
        "card_number": synth_card,
        "amount_cents": 4999,
        "discount_code": discount_code,
    }

    return {
        "sanitized_message": f"<untrusted_crash_log>{sanitized}</untrusted_crash_log>",
        "redaction_counts": {
            "emails": len(emails),
            "cards": len(cards) + len(ssns),
            "secrets": len(secrets),
            "injections": len(injections),
        },
        "synthetic_fixture": synthetic_fixture,
        "raw_payload_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
    }


def persist_airlock_scrub(
    external_ticket_ref: str,
    raw_report_text: str,
    idempotency_key: str,
    custom_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    with get_db(custom_db_path) as conn:
        existing = conn.execute(
            """
            SELECT r.redaction_id, r.incident_id, r.sanitized_message, r.synthetic_fixture_json,
                   r.emails_redacted, r.cards_redacted, r.secrets_redacted, r.injections_neutralized
            FROM airlock_redactions r
            WHERE r.idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        if existing:
            return {
                "incident_id": existing["incident_id"],
                "redaction_id": existing["redaction_id"],
                "sanitized_message": existing["sanitized_message"],
                "redaction_counts": {
                    "emails": existing["emails_redacted"],
                    "cards": existing["cards_redacted"],
                    "secrets": existing["secrets_redacted"],
                    "injections": existing["injections_neutralized"],
                },
                "synthetic_fixture": json.loads(existing["synthetic_fixture_json"]),
            }

        scrubbed = scrub_text(raw_report_text)
        incident_id = f"inc_{uuid.uuid4().hex[:10]}"
        redaction_id = f"red_{uuid.uuid4().hex[:10]}"
        retention_hours = int(os.getenv("AIRLOCK_RETENTION_HOURS", "24"))
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=retention_hours)).strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            """
            INSERT INTO incidents (incident_id, external_ticket_ref, status, suspect_commit)
            VALUES (?, ?, 'AIRLOCK_SCRUBBED', 'v2.14.0')
            """,
            (incident_id, external_ticket_ref),
        )
        counts = scrubbed["redaction_counts"]
        conn.execute(
            """
            INSERT INTO airlock_redactions (
                redaction_id, incident_id, idempotency_key, raw_payload_sha256,
                emails_redacted, cards_redacted, secrets_redacted, injections_neutralized,
                sanitized_message, synthetic_fixture_json, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                redaction_id,
                incident_id,
                idempotency_key,
                scrubbed["raw_payload_sha256"],
                counts["emails"],
                counts["cards"],
                counts["secrets"],
                counts["injections"],
                scrubbed["sanitized_message"],
                json.dumps(scrubbed["synthetic_fixture"]),
                expires_at,
            ),
        )

        return {
            "incident_id": incident_id,
            "redaction_id": redaction_id,
            "sanitized_message": scrubbed["sanitized_message"],
            "redaction_counts": counts,
            "synthetic_fixture": scrubbed["synthetic_fixture"],
        }
