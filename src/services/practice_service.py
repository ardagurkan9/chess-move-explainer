"""Interactive review of mistake positions with deterministic scheduling."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import chess

from src.analysis import MoveAnalyzer, PositionAnalyzer
from src.commentary import CommentaryService
from src.mistake_detector import MistakeDetector
from src.models import (
    CommentaryResult,
    MoveAnalysis,
    MoveClassification,
    MoveQuality,
    ThemeDetection,
    UserLevel,
)
from src.move_classifier import MoveClassifier
from src.repositories.interfaces import (
    GameHistoryRepository,
    PracticeGame,
    PracticePosition,
)


class PracticeMoveError(ValueError):
    """Raised when a submitted review move cannot be evaluated."""


@dataclass(frozen=True, slots=True)
class PracticeAttemptResult:
    """Outcome and optional coaching analysis for one review answer."""

    correct: bool
    attempted_move: str
    best_move: str
    updated_position: PracticePosition
    analysis: MoveAnalysis | None = None
    classification: MoveClassification | None = None
    theme_detection: ThemeDetection | None = None
    commentary: CommentaryResult | None = None


class PracticeService:
    """Load due positions, evaluate answers, and schedule future reviews."""

    def __init__(
        self,
        repository: GameHistoryRepository,
        engine: PositionAnalyzer,
        commentary: CommentaryService,
        *,
        username: str,
        depth: int = 12,
    ) -> None:
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("Username cannot be empty.")
        self.repository = repository
        self.move_analyzer = MoveAnalyzer(engine)
        self.commentary = commentary
        self.username = clean_username
        self.depth = depth
        self.classifier = MoveClassifier()
        self.mistake_detector = MistakeDetector()

    def next_position(self, *, now: datetime | None = None) -> PracticePosition | None:
        """Return the next position whose review time has arrived."""
        return self.repository.due_practice_position(
            username=self.username,
            as_of=now or datetime.now(timezone.utc),
        )

    def games(self, *, now: datetime | None = None) -> tuple[PracticeGame, ...]:
        """Return saved games containing mistake positions."""
        return self.repository.practice_games(
            username=self.username,
            as_of=now or datetime.now(timezone.utc),
        )

    def positions_for_game(
        self, game_id: int, *, now: datetime | None = None
    ) -> tuple[PracticePosition, ...]:
        """Return due mistakes for the selected game."""
        return self.repository.practice_positions_for_game(
            username=self.username,
            game_id=game_id,
            as_of=now or datetime.now(timezone.utc),
        )

    def submit(
        self,
        position: PracticePosition,
        move_text: str,
        *,
        level: UserLevel,
        now: datetime | None = None,
    ) -> PracticeAttemptResult:
        """Evaluate an exact best-move answer and persist its next review."""
        if not position.solution_moves:
            raise PracticeMoveError("The practice position has no stored solution.")
        try:
            move = chess.Move.from_uci(move_text.strip().lower())
            board = chess.Board(position.fen)
        except (chess.InvalidMoveError, ValueError) as error:
            raise PracticeMoveError("Enter a valid UCI move such as e2e4.") from error
        if move not in board.legal_moves:
            raise PracticeMoveError(f"Move {move.uci()} is illegal in this position.")

        best_move = position.solution_moves[0]
        correct = move.uci() == best_move
        current_time = now or datetime.now(timezone.utc)
        status, solved, next_review = self._schedule(
            correct=correct,
            successful_attempts=position.successful_attempts,
            now=current_time,
        )

        analysis = None
        classification = None
        detection = None
        explanation = None
        if not correct:
            analysis = self.move_analyzer.analyze_move(
                board, move, depth=self.depth
            )
            classification = self.classifier.classify(analysis)
            if classification.quality in {
                MoveQuality.INACCURACY,
                MoveQuality.MISTAKE,
                MoveQuality.BLUNDER,
            }:
                detection = self.mistake_detector.detect(analysis, classification)
            explanation = self.commentary.generate_for_review(
                analysis,
                classification,
                level=level,
                theme_detection=detection,
            )

        updated = self.repository.record_practice_attempt(
            username=self.username,
            position_id=position.id,
            attempted_move=move.uci(),
            correct=correct,
            quality=classification.quality if classification is not None else None,
            detected_theme=detection.theme if detection is not None else None,
            commentary=explanation.text if explanation is not None else None,
            commentary_source=(
                explanation.source if explanation is not None else None
            ),
            status=status,
            solved=solved,
            next_review_at=next_review,
        )
        return PracticeAttemptResult(
            correct=correct,
            attempted_move=move.uci(),
            best_move=best_move,
            updated_position=updated,
            analysis=analysis,
            classification=classification,
            theme_detection=detection,
            commentary=explanation,
        )

    @staticmethod
    def _schedule(
        *, correct: bool, successful_attempts: int, now: datetime
    ) -> tuple[str, bool, datetime]:
        if not correct:
            return "learning", False, now + timedelta(days=1)

        successes = successful_attempts + 1
        intervals = {1: 1, 2: 3, 3: 7}
        days = intervals.get(successes, 14)
        status = "mastered" if successes >= 4 else "learning"
        return status, True, now + timedelta(days=days)
