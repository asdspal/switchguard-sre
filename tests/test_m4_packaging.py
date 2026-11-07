from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_dockerfile_exists_and_exposes_8090():
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8090" in dockerfile
    assert "demo_app.main:app" in dockerfile


def test_docker_compose_valid_yaml_and_volumes():
    compose = yaml.safe_load((ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8"))
    svc = compose["services"]["switchguard-sre"]
    assert "8090:8090" in svc["ports"]
    assert "./data:/app/data" in svc["volumes"]
    assert "./postmortems:/app/postmortems" in svc["volumes"]
