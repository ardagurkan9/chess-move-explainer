from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.models import CommentaryResult, EngineResult, MistakeTheme, UserLevel
from src.repositories.interfaces import PracticePosition
from src.services.practice_service import PracticeMoveError, PracticeService


NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self, position: PracticePosition) -> None:
        self.position = position
        self.last_attempt: dict[str, object] | None = None

    def due_practice_position(self, *, username: str, as_of: datetime):
        return self.position if self.position.next_review_at is None or self.position.next_review_at <= as_of else None

    def practice_games(self, *, username: str, as_of: datetime):
        return ("game-list", username, as_of)

    def practice_positions_for_game(self, *, username: str, game_id: int, as_of: datetime):
        return (self.position,) if game_id == 1 else ()

    def record_practice_attempt(self, **values):
        self.last_attempt = values
        self.position = replace(
            self.position,
            attempts=self.position.attempts + 1,
            successful_attempts=(
                self.position.successful_attempts + int(values["correct"])
            ),
            status=values["status"],
            next_review_at=values["next_review_at"],
        )
        return self.position


def position(*, successes: int = 0) -> PracticePosition:
    return PracticePosition(
        id=1,
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        theme=MistakeTheme.GENERAL_ERROR,
        evidence=("Stockfish preferred e2e4.",),
        solution_moves=("e2e4",),
        status="new",
        attempts=successes,
        successful_attempts=successes,
        next_review_at=None,
    )


def service(position_value: PracticePosition):
    repository = FakeRepository(position_value)
    engine = MagicMock()
    commentary = MagicMock()
    result = PracticeService(repository, engine, commentary, username="student")
    return result, repository, engine, commentary


def test_correct_answer_is_scheduled_without_engine_or_ai_call() -> None:
    practice, repository, engine, commentary = service(position())

    result = practice.submit(
        repository.position, "e2e4", level=UserLevel.BEGINNER, now=NOW
    )

    assert result.correct is True
    assert result.updated_position.successful_attempts == 1
    assert result.updated_position.next_review_at == NOW + timedelta(days=1)
    engine.analyze.assert_not_called()
    commentary.generate_for_review.assert_not_called()


def test_practice_service_lists_games_and_positions_for_selected_game() -> None:
    practice, repository, _, _ = service(position())

    games = practice.games(now=NOW)
    positions = practice.positions_for_game(1, now=NOW)

    assert games == ("game-list", "student", NOW)
    assert positions == (repository.position,)


def test_wrong_legal_answer_is_analyzed_and_explained() -> None:
    practice, repository, engine, commentary = service(position())
    engine.analyze.side_effect = (
        EngineResult("e2e4", 100, None, ("e2e4",), 12),
        EngineResult("g1h1", -200, None, ("g1h1",), 12),
    )
    commentary.generate_for_review.return_value = CommentaryResult(
        "The king move misses the stronger continuation.",
        UserLevel.BEGINNER,
        source="gemini",
    )

    result = practice.submit(
        repository.position, "d2d4", level=UserLevel.BEGINNER, now=NOW
    )

    assert result.correct is False
    assert result.analysis is not None
    assert result.analysis.centipawn_loss == 300
    assert result.commentary is not None
    assert result.commentary.source == "gemini"
    assert result.updated_position.successful_attempts == 0
    assert result.updated_position.next_review_at == NOW + timedelta(days=1)
    assert engine.analyze.call_count == 2
    commentary.generate_for_review.assert_called_once()
    assert repository.last_attempt is not None
    assert repository.last_attempt["attempted_move"] == "d2d4"
    assert repository.last_attempt["commentary_source"] == "gemini"


@pytest.mark.parametrize(
    ("successes", "days", "status"),
    [(0, 1, "learning"), (1, 3, "learning"), (2, 7, "learning"), (3, 14, "mastered")],
)
def test_correct_answers_use_spaced_review_intervals(
    successes: int, days: int, status: str
) -> None:
    practice, repository, _, _ = service(position(successes=successes))

    result = practice.submit(
        repository.position, "e2e4", level=UserLevel.INTERMEDIATE, now=NOW
    )

    assert result.updated_position.status == status
    assert result.updated_position.next_review_at == NOW + timedelta(days=days)


@pytest.mark.parametrize("move", ["not-a-move", "e2e5"])
def test_invalid_or_illegal_answer_is_rejected(move: str) -> None:
    practice, repository, _, _ = service(position())

    with pytest.raises(PracticeMoveError):
        practice.submit(
            repository.position, move, level=UserLevel.BEGINNER, now=NOW
        )
