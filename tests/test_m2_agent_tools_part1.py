import pytest
from demo_app.db import init_db, update_service_version, get_db
from tools.airlock_scrub import run_airlock_cli
from tools.repro_checkout_500 import execute_repro_probe


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_tools1.db")
    monkeypatch.setenv("SWITCHGUARD_DB_PATH", db_file)
    monkeypatch.setenv("SWITCHGUARD_API_URL", "http://127.0.0.1:59999")
    init_db(db_file)
    yield db_file


def test_airlock_cli_fallback_persists_and_scrubs():
    res = run_airlock_cli(
        "SUP-501",
        "Customer ceo@enterprise.com card 4532015112830366 failed checkout on SWITCH20",
    )
    assert "ceo@enterprise.com" not in res["sanitized_message"]
    assert res["redaction_counts"]["emails"] == 1
    assert res["redaction_counts"]["cards"] == 1


def test_repro_probe_captures_500_on_v214_and_updates_incident():
    inc = run_airlock_cli("SUP-502", "Customer a@b.com crashed on SWITCH20")
    probe = execute_repro_probe(inc["incident_id"])
    assert probe["status_code"] == 500
    assert "KeyError" in probe["body"]["exception"]

    with get_db() as conn:
        row = conn.execute(
            "SELECT status, repro_exit_code FROM incidents WHERE incident_id = ?",
            (inc["incident_id"],),
        ).fetchone()
        assert row["status"] == "REPRODUCED"
        assert row["repro_exit_code"] == 1


def test_repro_probe_passes_200_when_rolled_back_to_v2132():
    update_service_version("v2.13.2", False)
    probe = execute_repro_probe()
    assert probe["status_code"] == 200
    assert probe["body"]["version"] == "v2.13.2"
