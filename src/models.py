"""Shared application data models."""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class EngineResult:
    """A normalized Stockfish position analysis.

    Scores always use White's perspective: positive values favor White and
    negative values favor Black. Exactly one of ``score_cp`` and ``mate`` is
    populated.
    """

    best_move: str
    score_cp: int | None
    mate: int | None
    pv: tuple[str, ...]
    depth: int | None = None

    @property
    def is_mate(self) -> bool:
        """Return whether Stockfish reported a forced mate."""
        return self.mate is not None


@dataclass(frozen=True, slots=True)
class MoveAnalysis:
    """Comparison of a position before and after a player's move."""

    played_move: str
    player_is_white: bool
    fen_before: str
    fen_after: str
    before: EngineResult
    after: EngineResult
    centipawn_loss: int | None
    missed_forced_mate: bool = False
    allowed_forced_mate: bool = False

    @property
    def best_move(self) -> str:
        """Return Stockfish's best move in the position before the move."""
        return self.before.best_move

    @property
    def contains_mate_score(self) -> bool:
        """Return whether either position contains a forced-mate score."""
        return self.before.is_mate or self.after.is_mate


class MoveQuality(StrEnum):
    """Supported move-quality labels."""

    BEST = "Best"
    EXCELLENT = "Excellent"
    GOOD = "Good"
    INACCURACY = "Inaccuracy"
    MISTAKE = "Mistake"
    BLUNDER = "Blunder"


@dataclass(frozen=True, slots=True)
class MoveClassification:
    """A move-quality label with a machine-readable explanation."""

    quality: MoveQuality
    reason: str
    centipawn_loss: int | None


class UserLevel(StrEnum):
    """Explanation detail levels supported by the coach."""

    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


@dataclass(frozen=True, slots=True)
class CommentaryResult:
    """A user-facing explanation and its provenance."""

    text: str
    level: UserLevel
    source: str = "template"
    fallback_reason: str | None = None
