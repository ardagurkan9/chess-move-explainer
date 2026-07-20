"""Repository contracts used by application services."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.models import (
    AnalyzedMove,
    GameReport,
    MistakeTheme,
    MoveQuality,
    UserLevel,
)


@dataclass(frozen=True, slots=True)
class MistakeSummary:
    """Number of persisted mistakes belonging to one theme."""

    theme: MistakeTheme
    count: int


@dataclass(frozen=True, slots=True)
class PracticePosition:
    """A due mistake position that can be presented without exposing ORM models."""

    id: int
    fen: str
    theme: MistakeTheme
    evidence: tuple[str, ...]
    solution_moves: tuple[str, ...]
    status: str
    attempts: int
    successful_attempts: int
    next_review_at: datetime | None
    game_id: int | None = None
    played_move: str | None = None
    ply_number: int | None = None


@dataclass(frozen=True, slots=True)
class PracticeGame:
    """A completed game containing saved mistake positions."""

    id: int
    completed_at: datetime
    result: str
    mistake_count: int
    due_count: int


@dataclass(frozen=True, slots=True)
class ProgressSummary:
    """Persisted game and practice metrics for one user."""

    total_games: int
    total_analyzed_moves: int
    total_mistakes: int
    mistake_counts: tuple[MistakeSummary, ...]
    pending_positions: int
    learning_positions: int
    mastered_positions: int
    due_positions: int
    total_practice_attempts: int
    correct_practice_attempts: int
    success_rate: float | None
    recent_success_rate: float | None
    previous_success_rate: float | None
    success_rate_change: float | None
    next_review_at: datetime | None

    @property
    def most_common_mistake(self) -> MistakeSummary | None:
        """Return the most frequent deterministic theme, if one exists."""
        return self.mistake_counts[0] if self.mistake_counts else None


class GameHistoryRepository(Protocol):
    """Persistence operations required by the coaching history service."""

    def save_game(
        self,
        *,
        username: str,
        level: UserLevel,
        report: GameReport,
        analyzed_moves: tuple[AnalyzedMove, ...],
    ) -> int:
        """Persist one completed game and return its identifier."""

    def recurring_mistakes(self, *, username: str) -> tuple[MistakeSummary, ...]:
        """Return persisted mistake counts ordered from most common to least."""

    def progress_summary(
        self, *, username: str, as_of: datetime
    ) -> ProgressSummary:
        """Aggregate the current user's game and practice progress."""

    def due_practice_position(
        self, *, username: str, as_of: datetime
    ) -> PracticePosition | None:
        """Return the next practice position due for a user."""

    def practice_games(
        self, *, username: str, as_of: datetime
    ) -> tuple[PracticeGame, ...]:
        """List completed games that contain generated practice positions."""

    def practice_positions_for_game(
        self, *, username: str, game_id: int, as_of: datetime
    ) -> tuple[PracticePosition, ...]:
        """List due practice positions belonging to one owned game."""

    def record_practice_attempt(
        self,
        *,
        username: str,
        position_id: int,
        attempted_move: str,
        correct: bool,
        quality: MoveQuality | None,
        detected_theme: MistakeTheme | None,
        commentary: str | None,
        commentary_source: str | None,
        status: str,
        solved: bool,
        next_review_at: datetime,
    ) -> PracticePosition:
        """Record one answer and return the updated position."""
