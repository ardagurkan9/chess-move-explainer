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


@dataclass(frozen=True, slots=True)
class MoveContext:
    """Deterministic board facts that can safely ground coaching text."""

    piece: str
    from_square: str
    to_square: str
    facts: tuple[str, ...]


class MistakeTheme(StrEnum):
    """Deterministically detectable mistake themes."""

    HANGING_PIECE = "HANGING_PIECE"
    MISSED_MATE = "MISSED_MATE"
    ALLOWED_MATE = "ALLOWED_MATE"
    MATERIAL_LOSS = "MATERIAL_LOSS"
    KING_SAFETY = "KING_SAFETY"
    GENERAL_ERROR = "GENERAL_ERROR"


@dataclass(frozen=True, slots=True)
class ThemeDetection:
    """A mistake theme supported by explicit chess evidence."""

    theme: MistakeTheme
    evidence: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Theme confidence must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class AnalyzedMove:
    """A user move together with its analysis and quality label."""

    analysis: MoveAnalysis
    classification: MoveClassification
    theme_detection: ThemeDetection | None = None
    commentary: CommentaryResult | None = None


@dataclass(frozen=True, slots=True)
class GameReport:
    """Aggregated coaching data for one completed game."""

    result: str
    player_is_white: bool
    total_user_moves: int
    average_centipawn_loss: float | None
    quality_counts: dict[MoveQuality, int]
    theme_counts: dict[MistakeTheme, int]
    missed_mates: int
    allowed_mates: int
    biggest_error: AnalyzedMove | None
    improvement_areas: tuple[str, ...]
    pgn: str
