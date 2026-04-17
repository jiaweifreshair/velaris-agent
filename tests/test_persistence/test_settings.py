"""存储配置相关测试。"""

from __future__ import annotations

from pathlib import Path

from openharness.config.settings import Settings, load_settings


def test_storage_settings_defaults():
    """Settings 应提供默认的 storage 配置。"""

    settings = Settings()

    assert settings.storage.postgres_dsn == ""
    assert settings.storage.evidence_dir is None
    assert settings.storage.job_poll_interval_seconds == 2.0
    assert settings.storage.job_max_attempts == 3


def test_load_settings_applies_storage_env_overrides(tmp_path: Path, monkeypatch):
    """环境变量应写入 settings.storage.*。"""

    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("VELARIS_POSTGRES_DSN", "postgresql://user:pass@localhost:5432/velaris")
    monkeypatch.setenv("VELARIS_EVIDENCE_DIR", str(tmp_path / "evidence"))

    settings = load_settings(path)

    assert settings.storage.postgres_dsn == "postgresql://user:pass@localhost:5432/velaris"
    assert settings.storage.evidence_dir == str(tmp_path / "evidence")
