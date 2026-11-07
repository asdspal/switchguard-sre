from pathlib import Path
import pytest
from demo_app.db import init_db
from tools.airlock_scrub import run_airlock_cli
from tools.repro_checkout_500 import execute_repro_probe
from tools.flashprove_verify import run_flashprove_cli
from tools.rollback_release import run_rollback_cli

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_tools2.db")
    monkeypatch.setenv("SWITCHGUARD_DB_PATH", db_file)
    monkeypatch.setenv("SWITCHGUARD_API_URL", "http://127.0.0.1:59999")
    init_db(db_file)
    yield db_file


def test_flashprove_cli_valid_and_tampered():
    inc = run_airlock_cli("SUP-600", "User a@b.com crashed")
    valid_path = str(ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json")
    tampered_path = str(ROOT_DIR / "fixtures" / "flashprove" / "tampered_model.json")

    ok_res = run_flashprove_cli(inc["incident_id"], valid_path)
    assert ok_res["is_verified"] is True
    assert ok_res["http_status"] == 200

    bad_res = run_flashprove_cli(inc["incident_id"], tampered_path)
    assert bad_res["is_verified"] is False
    assert bad_res["http_status"] == 422


def test_rollback_cli_rejects_unapproved_phrase():
    inc = run_airlock_cli("SUP-601", "User a@b.com crashed")
    valid_path = str(ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json")
    fp = run_flashprove_cli(inc["incident_id"], valid_path)

    with pytest.raises(RuntimeError, match="403"):
        run_rollback_cli(
            incident_id=inc["incident_id"],
            attestation_id=fp["attestation_id"],
            approved_by="@priya",
            approval_msg="Wrong phrase",
        )


def test_full_cli_pipeline_generates_postmortem_markdown(tmp_path):
    inc = run_airlock_cli("SUP-602", "Customer cto@fintech.io card 4532015112830366 failed on SWITCH20")
    repro = execute_repro_probe(inc["incident_id"])
    assert repro["status_code"] == 500

    valid_path = str(ROOT_DIR / "fixtures" / "flashprove" / "valid_maverick_400b.json")
    fp = run_flashprove_cli(inc["incident_id"], valid_path)
    assert fp["is_verified"] is True

    pm_dir = str(tmp_path / "pm")
    rb = run_rollback_cli(
        incident_id=inc["incident_id"],
        attestation_id=fp["attestation_id"],
        approved_by="@priya-sre",
        approval_msg="@-release-commander Approved. Roll back to v2.13.2",
        postmortem_dir=pm_dir,
    )
    assert rb["health"]["active_version"] == "v2.13.2"
    assert rb["post_rollback_checkout_status"] == 200
    assert rb["incident_status"] == "POSTMORTEM_PUBLISHED"

    pm_text = Path(rb["postmortem_file"]).read_text(encoding="utf-8")
    assert inc["incident_id"] in pm_text
    assert "0 Bytes" in pm_text
    assert "q/2^124 + 2^-101" in pm_text
