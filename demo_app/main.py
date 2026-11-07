import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from demo_app.db import init_db, get_db, get_service_state, update_service_version
from demo_app.airlock import persist_airlock_scrub, luhn_is_valid
from demo_app.flashprove import verify_and_record_proof
from demo_app.dashboard import render_dashboard_html


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SwitchGuard SRE & Target Cart-Service API",
    version="1.0.0",
    lifespan=lifespan,
)


def require_agent_key(x_agent_key: Optional[str] = Header(default=None)):
    expected = os.getenv("SWITCHGUARD_AGENT_KEY", "sg_agent_dev_key_2026")
    if x_agent_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Agent-Key header")


def require_admin_token(x_admin_token: Optional[str] = Header(default=None)):
    expected = os.getenv("SWITCHGUARD_ADMIN_TOKEN", "sg_admin_rollback_secret_2026")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token header")


class CheckoutRequest(BaseModel):
    customer_email: str
    card_number: str = Field(..., min_length=13, max_length=19)
    amount_cents: int = Field(..., gt=0)
    discount_code: Optional[str] = None


class AirlockScrubRequest(BaseModel):
    external_ticket_ref: str
    raw_report_text: str


class ReproRecordRequest(BaseModel):
    repro_exit_code: int
    repro_traceback: str
    suspect_commit: str = "v2.14.0"


class FlashProveVerifyRequest(BaseModel):
    incident_id: str
    model_name: str
    weight_commitment_hash: str
    proof_sha256: str
    token_count: int = Field(..., ge=1, le=1024)
    diagnostic_claim: Optional[str] = None
    simulated_verify_duration_ms: Optional[int] = None


class RollbackRequest(BaseModel):
    incident_id: str
    attestation_id: str
    target_version: str = "v2.13.2"
    approved_by_human: str
    approval_chat_message: str


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
def ui_dashboard():
    summary = api_list_incidents()
    return HTMLResponse(content=render_dashboard_html(summary), status_code=200)


@app.get("/api/v1/health")
def api_health():
    return get_service_state()


@app.post("/api/v1/checkout")
def api_checkout(payload: CheckoutRequest):
    if not luhn_is_valid(payload.card_number):
        raise HTTPException(status_code=400, detail="Invalid card number (failed Luhn check)")

    state = get_service_state()
    active_version = state["active_version"]

    # Deterministic v2.14.0 regression when discount_code is supplied (R-005)
    if active_version == "v2.14.0" and state["fault_mode_enabled"] and payload.discount_code:
        promo_table_v214 = {"SWITCH20": {"pct_off": 0.20}, "VIP10": {"pct_off": 0.10}}
        promo_entry = promo_table_v214.get(payload.discount_code, {"pct_off": 0.0})
        try:
            # Intentional regression in v2.14.0: looks up 'discount_rate' instead of 'pct_off'
            _ = promo_entry["discount_rate"]
        except KeyError as exc:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "version": active_version,
                    "exception": f"KeyError: {exc} in calculate_discount (commit v2.14.0)",
                },
            )

    discount_multiplier = 0.80 if payload.discount_code else 1.0
    charged = int(round(payload.amount_cents * discount_multiplier))
    return {
        "order_id": f"ord_{uuid.uuid4().hex[:8]}",
        "charged_cents": charged,
        "version": active_version,
    }


@app.post("/api/v1/airlock/scrub")
def api_airlock_scrub(
    payload: AirlockScrubRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_agent_key: Optional[str] = Header(default=None),
):
    require_agent_key(x_agent_key)
    return persist_airlock_scrub(
        external_ticket_ref=payload.external_ticket_ref,
        raw_report_text=payload.raw_report_text,
        idempotency_key=idempotency_key,
    )


@app.post("/api/v1/incidents/{incident_id}/repro")
def api_record_repro(
    incident_id: str,
    payload: ReproRecordRequest,
    x_agent_key: Optional[str] = Header(default=None),
):
    require_agent_key(x_agent_key)
    with get_db() as conn:
        row = conn.execute("SELECT incident_id FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
        conn.execute(
            """
            UPDATE incidents
            SET status = 'REPRODUCED', repro_exit_code = ?, repro_traceback = ?,
                suspect_commit = ?, updated_at = CURRENT_TIMESTAMP
            WHERE incident_id = ?
            """,
            (payload.repro_exit_code, payload.repro_traceback, payload.suspect_commit, incident_id),
        )
    return {"incident_id": incident_id, "status": "REPRODUCED", "suspect_commit": payload.suspect_commit}


@app.post("/api/v1/flashprove/verify")
def api_flashprove_verify(
    payload: FlashProveVerifyRequest,
    x_agent_key: Optional[str] = Header(default=None),
):
    require_agent_key(x_agent_key)
    result = verify_and_record_proof(
        incident_id=payload.incident_id,
        model_name=payload.model_name,
        weight_commitment_hash=payload.weight_commitment_hash,
        proof_sha256=payload.proof_sha256,
        token_count=payload.token_count,
        diagnostic_claim=payload.diagnostic_claim,
        simulated_verify_duration_ms=payload.simulated_verify_duration_ms,
    )
    if not result["is_verified"]:
        return JSONResponse(status_code=422, content=result)
    return result


@app.post("/api/v1/admin/rollback")
def api_admin_rollback(
    payload: RollbackRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin_token(x_admin_token)

    if "Approved. Roll back to v2.13.2" not in payload.approval_chat_message:
        raise HTTPException(
            status_code=403,
            detail="Human approval phrase 'Approved. Roll back to v2.13.2' missing from approval_chat_message",
        )

    with get_db() as conn:
        existing_rb = conn.execute(
            "SELECT * FROM rollback_audit_log WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing_rb:
            return {
                "rollback_id": existing_rb["rollback_id"],
                "incident_id": existing_rb["incident_id"],
                "previous_version": existing_rb["from_version"],
                "active_version": existing_rb["to_version"],
                "post_rollback_http_status": existing_rb["post_rollback_http_status"],
                "status": "ROLLED_BACK",
            }

        att = conn.execute(
            "SELECT is_verified FROM flashprove_attestations WHERE attestation_id = ? AND incident_id = ?",
            (payload.attestation_id, payload.incident_id),
        ).fetchone()
        if not att or att["is_verified"] != 1:
            raise HTTPException(
                status_code=403,
                detail="Rollback blocked: FlashProve attestation is missing or failed verification",
            )

    prev_state = get_service_state()
    new_state = update_service_version(payload.target_version, False)
    rollback_id = f"rb_{uuid.uuid4().hex[:10]}"
    postmortem_name = "incident-postmortem.md"

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO rollback_audit_log (
                rollback_id, incident_id, attestation_id, idempotency_key,
                from_version, to_version, approved_by_human, approval_chat_message,
                post_rollback_http_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 200)
            """,
            (
                rollback_id,
                payload.incident_id,
                payload.attestation_id,
                idempotency_key,
                prev_state["active_version"],
                new_state["active_version"],
                payload.approved_by_human,
                payload.approval_chat_message,
            ),
        )
        conn.execute(
            """
            UPDATE incidents
            SET status = 'ROLLED_BACK', postmortem_doc_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE incident_id = ?
            """,
            (postmortem_name, payload.incident_id),
        )

    return {
        "rollback_id": rollback_id,
        "incident_id": payload.incident_id,
        "previous_version": prev_state["active_version"],
        "active_version": new_state["active_version"],
        "post_rollback_http_status": 200,
        "status": "ROLLED_BACK",
    }


@app.post("/api/v1/admin/inject-fault")
def api_inject_fault(x_admin_token: Optional[str] = Header(default=None)):
    require_admin_token(x_admin_token)
    return update_service_version("v2.14.0", True)


@app.get("/api/v1/incidents")
def api_list_incidents():
    state = get_service_state()
    with get_db() as conn:
        totals_row = conn.execute(
            """
            SELECT
                COALESCE(SUM(emails_redacted), 0) AS emails_redacted,
                COALESCE(SUM(cards_redacted), 0) AS cards_redacted,
                COALESCE(SUM(secrets_redacted), 0) AS secrets_redacted,
                COALESCE(SUM(injections_neutralized), 0) AS injections_blocked
            FROM airlock_redactions
            """
        ).fetchone()
        fp_row = conn.execute(
            "SELECT COUNT(*) AS verified_proofs FROM flashprove_attestations WHERE is_verified = 1"
        ).fetchone()

        rows = conn.execute(
            """
            SELECT
                i.incident_id, i.external_ticket_ref, i.status, i.suspect_commit,
                i.repro_exit_code, i.repro_traceback, i.postmortem_doc_name, i.created_at,
                r.sanitized_message, r.synthetic_fixture_json,
                f.attestation_id, f.weight_commitment_hash, f.is_verified, f.verify_duration_ms,
                rb.approved_by_human, rb.to_version
            FROM incidents i
            LEFT JOIN airlock_redactions r ON r.incident_id = i.incident_id
            LEFT JOIN flashprove_attestations f ON f.incident_id = i.incident_id
            LEFT JOIN rollback_audit_log rb ON rb.incident_id = i.incident_id
            ORDER BY i.created_at DESC
            """
        ).fetchall()

    return {
        "service_state": state,
        "totals": {
            "emails_redacted": totals_row["emails_redacted"],
            "cards_redacted": totals_row["cards_redacted"],
            "secrets_redacted": totals_row["secrets_redacted"],
            "injections_blocked": totals_row["injections_blocked"],
            "verified_proofs": fp_row["verified_proofs"],
        },
        "incidents": [dict(r) for r in rows],
    }
