import json
from pathlib import Path
from fastapi.testclient import TestClient
from demo_app.main import app
from demo_app.db import init_db

ROOT_DIR = Path(__file__).resolve().parent.parent


def hex_to_rel_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = hex_to_rel_luminance(fg), hex_to_rel_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_design_tokens_wcag_aa_contrast_ratios():
    tokens = json.loads((ROOT_DIR / "blueprint" / "design-tokens.json").read_text(encoding="utf-8"))
    bg_primary = tokens["color"]["bg"]["primary"]["value"]
    bg_surface = tokens["color"]["bg"]["surface"]["value"]

    fg_colors = [
        tokens["color"]["text"]["primary"]["value"],
        tokens["color"]["text"]["secondary"]["value"],
        tokens["color"]["brand"]["primary"]["value"],
        tokens["color"]["semantic"]["success"]["value"],
        tokens["color"]["semantic"]["warning"]["value"],
        tokens["color"]["semantic"]["error"]["value"],
    ]
    for fg in fg_colors:
        assert contrast_ratio(fg, bg_primary) >= 4.5, f"{fg} on {bg_primary} failed WCAG AA 4.5:1"
        assert contrast_ratio(fg, bg_surface) >= 4.5, f"{fg} on {bg_surface} failed WCAG AA 4.5:1"


def test_dashboard_renders_landmarks_and_live_incidents(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_ui.db")
    monkeypatch.setenv("SWITCHGUARD_DB_PATH", db_file)
    init_db(db_file)
    client = TestClient(app)

    # Empty state check
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert 'role="main"' in res.text
    assert 'aria-live="polite"' in res.text
    assert "SwitchGuard SRE Ops Console" in res.text

    # Populated state check
    client.post(
        "/api/v1/airlock/scrub",
        headers={"X-Agent-Key": "sg_agent_dev_key_2026", "Idempotency-Key": "ui-1"},
        json={"external_ticket_ref": "SUP-UI-99", "raw_report_text": "User secret@acme.io crashed on SWITCH20"},
    )
    res2 = client.get("/dashboard")
    assert "SUP-UI-99" in res2.text
    assert "secret@acme.io" not in res2.text
    assert "[EMAIL_REDACTED]" in res2.text


def test_root_redirects_to_dashboard(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_ui2.db")
    monkeypatch.setenv("SWITCHGUARD_DB_PATH", db_file)
    init_db(db_file)
    client = TestClient(app)
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "/dashboard"
