"""Application entry point for Explainable Chess Coach."""

from src.config import ConfigurationError, load_settings
from src.cli import TerminalGame
from src.commentary import create_commentary_service
from src.engine import EngineError, StockfishEngine


def main() -> None:
    """Start the terminal-based chess coach."""
    try:
        settings = load_settings()
        commentary = create_commentary_service(
            provider=settings.ai_provider,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
        )
        with StockfishEngine.from_settings(settings) as engine:
            TerminalGame(engine, commentary=commentary).run()
    except ConfigurationError as error:
        raise SystemExit(f"Configuration error: {error}") from error
    except EngineError as error:
        raise SystemExit(f"Stockfish error: {error}") from error
    except KeyboardInterrupt:
        print("\nGame stopped.")


if __name__ == "__main__":
    main()
