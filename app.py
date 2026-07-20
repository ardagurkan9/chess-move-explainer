"""Application entry point for Chess Improvement Coach."""

from src.config import ConfigurationError, load_settings
from src.cli import TerminalApplication, TerminalGame
from src.commentary import create_commentary_service
from src.database import Database
from src.engine import EngineError, StockfishEngine
from src.repositories.sqlalchemy_repository import SQLAlchemyGameHistoryRepository
from src.services.history_service import HistoryService
from src.services.practice_service import PracticeService
from src.services.progress_service import ProgressService


def main() -> None:
    """Start the terminal-based chess coach."""
    try:
        settings = load_settings()
        commentary = create_commentary_service(
            provider=settings.ai_provider,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
        )
        database = Database(settings.database_url) if settings.database_url else None
        repository = (
            SQLAlchemyGameHistoryRepository(database)
            if database is not None
            else None
        )
        history_service = (
            HistoryService(repository, username=settings.coach_username)
            if repository is not None
            else None
        )
        try:
            with StockfishEngine.from_settings(settings) as engine:
                with StockfishEngine.from_settings(settings) as opponent_engine:
                    game = TerminalGame(
                        engine,
                        commentary=commentary,
                        history_service=history_service,
                        opponent_engine=opponent_engine,
                    )
                    practice_service = (
                        PracticeService(
                            repository,
                            engine,
                            commentary,
                            username=settings.coach_username,
                        )
                        if repository is not None
                        else None
                    )
                    progress_service = (
                        ProgressService(
                            repository,
                            username=settings.coach_username,
                        )
                        if repository is not None
                        else None
                    )
                    TerminalApplication(
                        game,
                        practice_service=practice_service,
                        progress_service=progress_service,
                    ).run()
        finally:
            if database is not None:
                database.close()
    except ConfigurationError as error:
        raise SystemExit(f"Configuration error: {error}") from error
    except EngineError as error:
        raise SystemExit(f"Stockfish error: {error}") from error
    except KeyboardInterrupt:
        print("\nGame stopped.")


if __name__ == "__main__":
    main()
