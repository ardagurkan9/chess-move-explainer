from pathlib import Path

import pytest

from src.config import ConfigurationError, load_settings


def test_load_settings_requires_stockfish_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)

    with pytest.raises(ConfigurationError, match="STOCKFISH_PATH is not set"):
        load_settings(env_file=tmp_path / "missing.env")


def test_load_settings_rejects_missing_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_path = tmp_path / "stockfish"
    monkeypatch.setenv("STOCKFISH_PATH", str(missing_path))

    with pytest.raises(ConfigurationError, match="does not exist"):
        load_settings()


def test_load_settings_reads_valid_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stockfish_path = tmp_path / "stockfish.exe"
    stockfish_path.touch()
    monkeypatch.setenv("STOCKFISH_PATH", str(stockfish_path))
    monkeypatch.setenv("AI_PROVIDER", "GEMINI")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "test-model")

    settings = load_settings()

    assert settings.stockfish_path == stockfish_path.resolve()
    assert settings.ai_provider == "gemini"
    assert settings.ai_api_key == "test-key"
    assert settings.ai_model == "test-model"
