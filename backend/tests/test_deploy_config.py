"""Keeps render.yaml in step with the settings the backend actually reads."""

from pathlib import Path

import pytest

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_render_blueprint_env_names_exist_in_settings():
    yaml = pytest.importorskip("yaml")
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    names = [v["key"] for svc in blueprint["services"] for v in svc.get("envVars", [])]
    unknown = [n for n in names if n not in Settings.model_fields]
    assert not unknown, f"render.yaml sets env vars the backend does not read: {unknown}"


def test_render_blueprint_has_required_secrets_marked_sync_false():
    yaml = pytest.importorskip("yaml")
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    env = {v["key"]: v for v in blueprint["services"][0]["envVars"]}
    for key in ("DATABASE_URL", "ADMIN_EMAIL", "ADMIN_PASSWORD", "CORS_ORIGINS", "ADMIN_WEB_URL"):
        assert env[key].get("sync") is False, f"{key} must be entered in the Render dashboard, not committed"
