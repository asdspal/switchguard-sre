import json
from pathlib import Path
from demo_app.db import init_db, get_db
from demo_app.airlock import persist_airlock_scrub
from demo_app.flashprove import verify_and_record_proof

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_valid_flashprove_bundle_passes(tmp_path):
    db_file = str(tmp_path / "test_fp.db")
    init_db(db_file)
    inc = persist_airlock_scrub("SUP-200", "User a@b.com crashed", "idem-200", db_file)
    bundle = json.loads((ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json").read_text())

    res = verify_and_record_proof(
        incident_id=inc["incident_id"],
        model_name=bundle["model_name"],
        weight_commitment_hash=bundle["weight_commitment_hash"],
        proof_sha256=bundle["proof_sha256"],
        token_count=bundle["token_count"],
        diagnostic_claim=bundle["diagnostic_claim"],
        simulated_verify_duration_ms=bundle["simulated_verify_duration_ms"],
        custom_db_path=db_file,
    )
    assert res["is_verified"] is True
    assert res["failure_reason"] is None

    with get_db(db_file) as conn:
        row = conn.execute("SELECT status FROM incidents WHERE incident_id = ?", (inc["incident_id"],)).fetchone()
        assert row["status"] == "PENDING_APPROVAL"


def test_tampered_flashprove_bundle_blocked(tmp_path):
    db_file = str(tmp_path / "test_fp2.db")
    init_db(db_file)
    inc = persist_airlock_scrub("SUP-201", "User a@b.com crashed", "idem-201", db_file)
    bundle = json.loads((ROOT_DIR / "fixtures" / "flashprove" / "tampered_model.json").read_text())

    res = verify_and_record_proof(
        incident_id=inc["incident_id"],
        model_name=bundle["model_name"],
        weight_commitment_hash=bundle["weight_commitment_hash"],
        proof_sha256=bundle["proof_sha256"],
        token_count=bundle["token_count"],
        diagnostic_claim=bundle["diagnostic_claim"],
        simulated_verify_duration_ms=bundle["simulated_verify_duration_ms"],
        custom_db_path=db_file,
    )
    assert res["is_verified"] is False
    assert "mismatch" in res["failure_reason"].lower()

    with get_db(db_file) as conn:
        row = conn.execute("SELECT status FROM incidents WHERE incident_id = ?", (inc["incident_id"],)).fetchone()
        assert row["status"] == "BLOCKED_TAMPERED"
