"""Environment-based application configuration."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated application settings."""

    stockfish_path: Path
    ai_provider: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None


def load_settings(*, env_file: str | Path | None = None) -> Settings:
    """Load settings and validate the configured Stockfish executable.

    Args:
        env_file: Optional dotenv file. When omitted, python-dotenv searches for
            a local ``.env`` file.

    Raises:
        ConfigurationError: If STOCKFISH_PATH is missing or invalid.
    """
    load_dotenv(dotenv_path=env_file)

    raw_stockfish_path = os.getenv("STOCKFISH_PATH", "").strip()
    if not raw_stockfish_path:
        raise ConfigurationError(
            "STOCKFISH_PATH is not set. Copy .env.example to .env and add the "
            "absolute path to your Stockfish executable."
        )

    stockfish_path = Path(raw_stockfish_path).expanduser()
    if not stockfish_path.is_file():
        raise ConfigurationError(
            f"The configured Stockfish executable does not exist: {stockfish_path}"
        )

    return Settings(
        stockfish_path=stockfish_path.resolve(),
        ai_provider=os.getenv("AI_PROVIDER", "").strip().lower() or None,
        ai_api_key=os.getenv("AI_API_KEY", "").strip() or None,
        ai_model=os.getenv("AI_MODEL", "").strip() or None,
    )
