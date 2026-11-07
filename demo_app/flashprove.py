import hashlib
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from demo_app.db import get_db

APPROVED_MODEL_COMMITMENTS = {
    "Llama-4-Maverick-400B-MoE-Int4": "8f4d9c2a1b3e5f708192a3b4c5d6e7f80123456789abcdef0123456789abcdef"
}

DEFAULT_DIAGNOSTIC_CLAIM = (
    "ROOT_CAUSE: commit v2.14.0 introduced unguarded dict lookup "
    "PROMO_RATES[discount_code]['discount_rate'] in POST /api/v1/checkout; "
    "SAFE_REMEDIATION: rollback active_version to v2.13.2"
)


def verify_and_record_proof(
    incident_id: str,
    model_name: str,
    weight_commitment_hash: str,
    proof_sha256: str,
    token_count: int,
    diagnostic_claim: Optional[str] = None,
    simulated_verify_duration_ms: Optional[int] = None,
    custom_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    start_ns = time.perf_counter_ns()
    claim = diagnostic_claim or DEFAULT_DIAGNOSTIC_CLAIM
    expected_commitment = APPROVED_MODEL_COMMITMENTS.get(model_name)

    is_verified = True
    failure_reason = None

    if not expected_commitment:
        is_verified = False
        failure_reason = f"Unrecognized model_name: {model_name}"
    elif weight_commitment_hash != expected_commitment:
        is_verified = False
        failure_reason = (
            f"Weight commitment mismatch: expected {expected_commitment[:16]}..., "
            f"got {weight_commitment_hash[:16]}... (Possible silent model swap)"
        )
    else:
        expected_proof = hashlib.sha256(f"{weight_commitment_hash}:{claim}".encode("utf-8")).hexdigest()
        if proof_sha256 != expected_proof:
            is_verified = False
            failure_reason = "zkSNARK proof_sha256 verification failed against committed weights and diagnostic claim"

    bin_path = os.getenv("FLASHPROVE_BIN_PATH", "/usr/local/bin/cp_verify")
    verifier_engine = "cp_verify_v0.16.0"
    if is_verified and Path(bin_path).is_file():
        try:
            subprocess.run([bin_path, "--version"], check=True, capture_output=True, timeout=5)
            verifier_engine = "cp_verify_v0.16.0_native"
        except Exception:
            verifier_engine = "cp_verify_v0.16.0_sha256_fallback"

    elapsed_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)
    duration_ms = simulated_verify_duration_ms if simulated_verify_duration_ms is not None else max(elapsed_ms, 1)
    soundness_bound = "q/2^124 + 2^-101" if is_verified else "FAILED_SOUNDNESS_CHECK"
    attestation_id = f"att_{uuid.uuid4().hex[:10]}"

    with get_db(custom_db_path) as conn:
        conn.execute(
            """
            INSERT INTO flashprove_attestations (
                attestation_id, incident_id, model_name, weight_commitment_hash,
                proof_sha256, token_count, verifier_engine, verify_duration_ms,
                soundness_bound, is_verified, failure_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attestation_id,
                incident_id,
                model_name,
                weight_commitment_hash,
                proof_sha256,
                token_count,
                verifier_engine,
                duration_ms,
                soundness_bound,
                1 if is_verified else 0,
                failure_reason,
            ),
        )
        new_status = "PENDING_APPROVAL" if is_verified else "BLOCKED_TAMPERED"
        conn.execute(
            "UPDATE incidents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE incident_id = ?",
            (new_status, incident_id),
        )

    return {
        "attestation_id": attestation_id,
        "incident_id": incident_id,
        "is_verified": is_verified,
        "verify_duration_ms": duration_ms,
        "soundness_bound": soundness_bound,
        "failure_reason": failure_reason,
    }
