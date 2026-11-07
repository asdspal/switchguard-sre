import hashlib
import json
import sqlite3
from pathlib import Path
import pytest
from demo_app.db import init_db, get_db, get_service_state, update_service_version

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_schema_tables_and_indexes_exist(tmp_path):
    db_file = str(tmp_path / "test_sg.db")
    init_db(db_file)
    with get_db(db_file) as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        expected_tables = {
            "runtime_config",
            "incidents",
            "airlock_redactions",
            "flashprove_attestations",
            "rollback_audit_log",
        }
        assert expected_tables.issubset(tables)

        indexes = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        expected_indexes = {
            "idx_incidents_status_created",
            "idx_airlock_incident_id",
            "idx_airlock_expires_at",
            "idx_flashprove_incident_verified",
            "idx_rollback_incident_id",
        }
        assert expected_indexes.issubset(indexes)


def test_seed_state_and_version_toggle(tmp_path):
    db_file = str(tmp_path / "test_sg.db")
    init_db(db_file)
    state = get_service_state(db_file)
    assert state["active_version"] == "v2.14.0"
    assert state["status"] == "degraded"

    updated = update_service_version("v2.13.2", False, db_file)
    assert updated["active_version"] == "v2.13.2"
    assert updated["status"] == "healthy"


def test_foreign_key_enforcement(tmp_path):
    db_file = str(tmp_path / "test_sg.db")
    init_db(db_file)
    with pytest.raises(sqlite3.IntegrityError):
        with get_db(db_file) as conn:
            conn.execute(
                """
                INSERT INTO airlock_redactions (
                    redaction_id, incident_id, idempotency_key, raw_payload_sha256,
                    sanitized_message, synthetic_fixture_json, expires_at
                ) VALUES ('r1', 'non_existent_inc', 'idem1', 'a'*64, 'msg', '{}', CURRENT_TIMESTAMP)
                """
            )


def test_env_example_completeness():
    env_text = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")
    required_keys = [
        "SWITCHGUARD_PORT",
        "SWITCHGUARD_DB_PATH",
        "CART_SERVICE_INITIAL_VERSION",
        "SWITCHGUARD_AGENT_KEY",
        "SWITCHGUARD_ADMIN_TOKEN",
        "AIRLOCK_RETENTION_HOURS",
        "FLASHPROVE_BIN_PATH",
        "FLASHPROVE_STRICT_MODE",
        "SWITCH_SERVER_URL",
        "MATTERMOST_URL",
    ]
    for key in required_keys:
        assert f"{key}=" in env_text


def test_flashprove_fixture_cryptographic_digest():
    valid_path = ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json"
    tampered_path = ROOT_DIR / "fixtures" / "flashprove" / "tampered_model.json"
    valid = json.loads(valid_path.read_text(encoding="utf-8"))
    tampered = json.loads(tampered_path.read_text(encoding="utf-8"))

    computed_valid = hashlib.sha256(
        f"{valid['weight_commitment_hash']}:{valid['diagnostic_claim']}".encode("utf-8")
    ).hexdigest()
    assert computed_valid == valid["proof_sha256"]

    computed_tampered = hashlib.sha256(
        f"{tampered['weight_commitment_hash']}:{tampered['diagnostic_claim']}".encode("utf-8")
    ).hexdigest()
    assert computed_tampered != tampered["proof_sha256"]
