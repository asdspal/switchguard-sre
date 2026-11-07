import json
from pathlib import Path
import pytest
from demo_app.db import init_db
from demo_app.airlock import scrub_text
from scripts.simulate_customer_crash import simulate_outage

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_five_scenario_evaluation_harness():
    eval_cases = json.loads((ROOT_DIR / "fixtures" / "evals" / "incidents_eval.json").read_text(encoding="utf-8"))
    assert len(eval_cases) == 5

    for case in eval_cases:
        res = scrub_text(case["raw_text"])
        counts = res["redaction_counts"]
        expected = case["expected_min_redactions"]
        assert counts["emails"] >= expected["emails"], f"Failed email scrub on {case['case_id']}"
        assert counts["cards"] >= expected["cards"], f"Failed card/SSN scrub on {case['case_id']}"
        assert counts["secrets"] >= expected["secrets"], f"Failed secret scrub on {case['case_id']}"
        assert counts["injections"] >= expected["injections"], f"Failed injection block on {case['case_id']}"


def test_full_simulator_pipeline_e2e(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_e2e.db")
    monkeypatch.setenv("SWITCHGUARD_DB_PATH", db_file)
    monkeypatch.setenv("SWITCHGUARD_API_URL", "http://127.0.0.1:59999")
    init_db(db_file)

    out = simulate_outage(run_pipeline=True)
    assert out["crash_status"] == 500
    assert out["pipeline"]["health"]["active_version"] == "v2.13.2"
    assert out["pipeline"]["post_rollback_checkout_status"] == 200
    assert out["pipeline"]["incident_status"] == "POSTMORTEM_PUBLISHED"
