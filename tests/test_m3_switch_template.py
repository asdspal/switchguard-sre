from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT_DIR / "switchguard-sre.template.yaml"


def load_template() -> dict:
    assert TEMPLATE_PATH.is_file(), "switchguard-sre.template.yaml must exist at repo root"
    return yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))


def test_template_top_level_sections():
    tpl = load_template()
    for section in ("params", "agents", "group", "rooms", "links"):
        assert section in tpl, f"Missing top-level section: {section}"
    assert "kickoff" not in tpl, "Group documents must not have a top-level kickoff"


def test_agents_addressing_and_tool_commands():
    tpl = load_template()
    agents = {a["name"]: a for a in tpl["agents"]}
    assert set(agents.keys()) == {"airlock-triager", "sre-repro", "release-commander"}

    # R-004: Tier-1 intake is anyone; Tier-2 repro and release commander are owner-agents
    assert agents["airlock-triager"]["addressing"] == "anyone"
    assert agents["sre-repro"]["addressing"] == "owner-agents"
    assert agents["release-commander"]["addressing"] == "owner-agents"

    # Current Switch schema requires provider, location and directory on every agent
    for agent in agents.values():
        assert agent.get("provider"), f"{agent['name']} missing provider"
        assert agent.get("location"), f"{agent['name']} missing location"
        assert agent.get("directory"), f"{agent['name']} missing directory"

    # Verify CLI scripts are referenced in instructions
    assert "tools/airlock_scrub.py" in agents["airlock-triager"]["instructions"]
    assert "tools/repro_checkout_500.py" in agents["sre-repro"]["instructions"]
    assert "tools/flashprove_verify.py" in agents["release-commander"]["instructions"]
    assert "tools/rollback_release.py" in agents["release-commander"]["instructions"]


def test_rooms_and_directional_airlock_link():
    tpl = load_template()
    rooms = {r["name"]: r for r in tpl["rooms"]}
    assert set(rooms.keys()) == {"alerts-intake", "incident-war-room"}
    assert rooms["alerts-intake"]["agents"] == ["airlock-triager"]
    assert set(rooms["incident-war-room"]["agents"]) == {"sre-repro", "release-commander"}

    links = tpl["links"]
    assert len(links) == 1
    assert links[0]["from"] == "alerts-intake"
    assert links[0]["to"] == "incident-war-room"


def test_human_approval_gate_and_no_voice_dependency():
    tpl = load_template()
    rc_prompt = next(a["instructions"] for a in tpl["agents"] if a["name"] == "release-commander")
    assert "Approved. Roll back to v2.13.2" in rc_prompt
    assert "incident-postmortem.md" in rc_prompt
    assert "wispr" not in rc_prompt.lower()
