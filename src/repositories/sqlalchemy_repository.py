"""SQLAlchemy repository for games, mistakes, and practice positions."""

import chess
from datetime import datetime

from sqlalchemy import case, func, or_, select

from src.database import Database
from src.db_models import (
    GameRecord,
    MistakeRecord,
    MoveAnalysisRecord,
    PlayerColor,
    PracticeAttemptRecord,
    PracticePositionRecord,
    PracticeStatus,
    UserRecord,
)
from src.models import AnalyzedMove, GameReport, MistakeTheme, MoveQuality, UserLevel
from src.repositories.interfaces import (
    MistakeSummary,
    PracticeGame,
    PracticePosition,
    ProgressSummary,
)


class SQLAlchemyGameHistoryRepository:
    """Persist coaching history through a shared ``Database`` instance."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def save_game(
        self,
        *,
        username: str,
        level: UserLevel,
        report: GameReport,
        analyzed_moves: tuple[AnalyzedMove, ...],
    ) -> int:
        """Save a completed game, its analyses, mistakes, and review positions."""
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("Username cannot be empty.")

        with self.database.session() as session:
            user = session.scalar(
                select(UserRecord).where(UserRecord.username == clean_username)
            )
            if user is None:
                user = UserRecord(username=clean_username, level=level)
                session.add(user)
            else:
                user.level = level

            game = GameRecord(
                user=user,
                player_color=(
                    PlayerColor.WHITE if report.player_is_white else PlayerColor.BLACK
                ),
                result=report.result,
                pgn=report.pgn,
            )
            session.add(game)

            for analyzed in analyzed_moves:
                analysis = analyzed.analysis
                move_record = MoveAnalysisRecord(
                    game=game,
                    ply_number=chess.Board(analysis.fen_before).ply() + 1,
                    played_move=analysis.played_move,
                    best_move=analysis.best_move,
                    fen_before=analysis.fen_before,
                    fen_after=analysis.fen_after,
                    score_before_cp=analysis.before.score_cp,
                    score_after_cp=analysis.after.score_cp,
                    mate_before=analysis.before.mate,
                    mate_after=analysis.after.mate,
                    centipawn_loss=analyzed.classification.centipawn_loss,
                    quality=analyzed.classification.quality,
                    principal_variation=list(analysis.before.pv),
                    commentary=(
                        analyzed.commentary.text if analyzed.commentary is not None else None
                    ),
                    commentary_source=(
                        analyzed.commentary.source
                        if analyzed.commentary is not None
                        else None
                    ),
                )
                session.add(move_record)

                detection = analyzed.theme_detection
                if detection is None:
                    continue
                mistake = MistakeRecord(
                    move_analysis=move_record,
                    theme=detection.theme,
                    evidence=list(detection.evidence),
                    confidence=detection.confidence,
                )
                session.add(
                    PracticePositionRecord(
                        user=user,
                        source_mistake=mistake,
                        fen=analysis.fen_before,
                        solution_moves=list(analysis.before.pv),
                    )
                )

            session.flush()
            game_id = game.id

        return game_id

    def recurring_mistakes(self, *, username: str) -> tuple[MistakeSummary, ...]:
        """Count mistake themes across every game belonging to a user."""
        statement = (
            select(MistakeRecord.theme, func.count(MistakeRecord.id))
            .join(MistakeRecord.move_analysis)
            .join(MoveAnalysisRecord.game)
            .join(GameRecord.user)
            .where(UserRecord.username == username.strip())
            .group_by(MistakeRecord.theme)
            .order_by(func.count(MistakeRecord.id).desc(), MistakeRecord.theme)
        )
        with self.database.session() as session:
            rows = session.execute(statement).all()
        return tuple(MistakeSummary(theme=theme, count=count) for theme, count in rows)

    def due_practice_position(
        self, *, username: str, as_of: datetime
    ) -> PracticePosition | None:
        """Return the oldest due position for the requested user."""
        statement = (
            select(PracticePositionRecord, MistakeRecord, MoveAnalysisRecord)
            .join(PracticePositionRecord.user)
            .join(PracticePositionRecord.source_mistake)
            .join(MistakeRecord.move_analysis)
            .where(
                UserRecord.username == username.strip(),
                or_(
                    PracticePositionRecord.next_review_at.is_(None),
                    PracticePositionRecord.next_review_at <= as_of,
                ),
            )
            .order_by(
                case(
                    (PracticePositionRecord.next_review_at.is_(None), 0),
                    else_=1,
                ),
                PracticePositionRecord.next_review_at,
                PracticePositionRecord.created_at,
            )
            .limit(1)
        )
        with self.database.session() as session:
            row = session.execute(statement).first()
            if row is None:
                return None
            position, mistake, move_analysis = row
            return self._practice_position(position, mistake, move_analysis)

    def practice_games(
        self, *, username: str, as_of: datetime
    ) -> tuple[PracticeGame, ...]:
        """List the user's games that produced at least one practice position."""
        due_expression = case(
            (
                or_(
                    PracticePositionRecord.next_review_at.is_(None),
                    PracticePositionRecord.next_review_at <= as_of,
                ),
                1,
            ),
            else_=0,
        )
        statement = (
            select(
                GameRecord.id,
                GameRecord.completed_at,
                GameRecord.result,
                func.count(PracticePositionRecord.id),
                func.sum(due_expression),
            )
            .join(GameRecord.user)
            .join(GameRecord.move_analyses)
            .join(MoveAnalysisRecord.mistake)
            .join(MistakeRecord.practice_positions)
            .where(UserRecord.username == username.strip())
            .group_by(GameRecord.id)
            .order_by(GameRecord.completed_at.desc(), GameRecord.id.desc())
        )
        with self.database.session() as session:
            rows = session.execute(statement).all()
        return tuple(
            PracticeGame(
                id=game_id,
                completed_at=completed_at,
                result=result,
                mistake_count=mistake_count,
                due_count=due_count or 0,
            )
            for game_id, completed_at, result, mistake_count, due_count in rows
        )

    def practice_positions_for_game(
        self, *, username: str, game_id: int, as_of: datetime
    ) -> tuple[PracticePosition, ...]:
        """Return due mistakes from one game owned by the selected user."""
        statement = (
            select(PracticePositionRecord, MistakeRecord, MoveAnalysisRecord)
            .join(PracticePositionRecord.user)
            .join(PracticePositionRecord.source_mistake)
            .join(MistakeRecord.move_analysis)
            .join(MoveAnalysisRecord.game)
            .where(
                UserRecord.username == username.strip(),
                GameRecord.id == game_id,
                or_(
                    PracticePositionRecord.next_review_at.is_(None),
                    PracticePositionRecord.next_review_at <= as_of,
                ),
            )
            .order_by(MoveAnalysisRecord.ply_number)
        )
        with self.database.session() as session:
            rows = session.execute(statement).all()
            return tuple(
                self._practice_position(position, mistake, move_analysis)
                for position, mistake, move_analysis in rows
            )

    def progress_summary(
        self, *, username: str, as_of: datetime
    ) -> ProgressSummary:
        """Aggregate portfolio-safe progress metrics from persisted records."""
        clean_username = username.strip()
        user_filter = UserRecord.username == clean_username
        with self.database.session() as session:
            total_games = session.scalar(
                select(func.count(GameRecord.id))
                .join(GameRecord.user)
                .where(user_filter)
            ) or 0
            total_moves = session.scalar(
                select(func.count(MoveAnalysisRecord.id))
                .join(MoveAnalysisRecord.game)
                .join(GameRecord.user)
                .where(user_filter)
            ) or 0
            mistake_rows = session.execute(
                select(MistakeRecord.theme, func.count(MistakeRecord.id))
                .join(MistakeRecord.move_analysis)
                .join(MoveAnalysisRecord.game)
                .join(GameRecord.user)
                .where(user_filter)
                .group_by(MistakeRecord.theme)
                .order_by(func.count(MistakeRecord.id).desc(), MistakeRecord.theme)
            ).all()
            status_rows = session.execute(
                select(PracticePositionRecord.status, func.count(PracticePositionRecord.id))
                .join(PracticePositionRecord.user)
                .where(user_filter)
                .group_by(PracticePositionRecord.status)
            ).all()
            attempt_rows = session.scalars(
                select(PracticeAttemptRecord.correct)
                .join(PracticeAttemptRecord.practice_position)
                .join(PracticePositionRecord.user)
                .where(user_filter)
                .order_by(
                    PracticeAttemptRecord.attempted_at.desc(),
                    PracticeAttemptRecord.id.desc(),
                )
                .limit(20)
            ).all()
            attempt_totals = session.execute(
                select(
                    func.count(PracticeAttemptRecord.id),
                    func.count(PracticeAttemptRecord.id).filter(
                        PracticeAttemptRecord.correct.is_(True)
                    ),
                )
                .join(PracticeAttemptRecord.practice_position)
                .join(PracticePositionRecord.user)
                .where(user_filter)
            ).one()
            due_positions = session.scalar(
                select(func.count(PracticePositionRecord.id))
                .join(PracticePositionRecord.user)
                .where(
                    user_filter,
                    or_(
                        PracticePositionRecord.next_review_at.is_(None),
                        PracticePositionRecord.next_review_at <= as_of,
                    ),
                )
            ) or 0
            next_review_at = session.scalar(
                select(func.min(PracticePositionRecord.next_review_at))
                .join(PracticePositionRecord.user)
                .where(
                    user_filter,
                    PracticePositionRecord.next_review_at > as_of,
                )
            )

        mistakes = tuple(
            MistakeSummary(theme=theme, count=count)
            for theme, count in mistake_rows
        )
        statuses = {status: count for status, count in status_rows}
        total_attempts, correct_attempts = attempt_totals
        recent = list(attempt_rows[:10])
        previous = list(attempt_rows[10:20])
        recent_rate = self._success_rate(recent)
        previous_rate = self._success_rate(previous) if len(previous) == 10 else None
        change = (
            recent_rate - previous_rate
            if recent_rate is not None and previous_rate is not None
            else None
        )
        return ProgressSummary(
            total_games=total_games,
            total_analyzed_moves=total_moves,
            total_mistakes=sum(item.count for item in mistakes),
            mistake_counts=mistakes,
            pending_positions=statuses.get(PracticeStatus.PENDING, 0),
            learning_positions=statuses.get(PracticeStatus.LEARNING, 0),
            mastered_positions=statuses.get(PracticeStatus.MASTERED, 0),
            due_positions=due_positions,
            total_practice_attempts=total_attempts,
            correct_practice_attempts=correct_attempts,
            success_rate=(
                correct_attempts / total_attempts if total_attempts else None
            ),
            recent_success_rate=recent_rate,
            previous_success_rate=previous_rate,
            success_rate_change=change,
            next_review_at=next_review_at,
        )

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
        """Update review counters and scheduling for one owned position."""
        statement = (
            select(PracticePositionRecord, MistakeRecord)
            .join(PracticePositionRecord.user)
            .join(PracticePositionRecord.source_mistake)
            .where(
                PracticePositionRecord.id == position_id,
                UserRecord.username == username.strip(),
            )
        )
        with self.database.session() as session:
            row = session.execute(statement).first()
            if row is None:
                raise LookupError("Practice position was not found for this user.")
            position, mistake = row
            position.attempts += 1
            if correct:
                position.successful_attempts += 1
            position.status = PracticeStatus(status)
            position.solved = solved
            position.next_review_at = next_review_at
            session.add(
                PracticeAttemptRecord(
                    practice_position=position,
                    attempted_move=attempted_move,
                    correct=correct,
                    quality=quality,
                    detected_theme=detected_theme,
                    commentary=commentary,
                    commentary_source=commentary_source,
                    scheduled_review_at=next_review_at,
                )
            )
            session.flush()
            return self._practice_position(position, mistake)

    @staticmethod
    def _practice_position(
        position: PracticePositionRecord,
        mistake: MistakeRecord,
        move_analysis: MoveAnalysisRecord | None = None,
    ) -> PracticePosition:
        return PracticePosition(
            id=position.id,
            fen=position.fen,
            theme=mistake.theme,
            evidence=tuple(mistake.evidence),
            solution_moves=tuple(position.solution_moves),
            status=position.status.value,
            attempts=position.attempts,
            successful_attempts=position.successful_attempts,
            next_review_at=position.next_review_at,
            game_id=move_analysis.game_id if move_analysis is not None else None,
            played_move=(
                move_analysis.played_move if move_analysis is not None else None
            ),
            ply_number=(
                move_analysis.ply_number if move_analysis is not None else None
            ),
        )

    @staticmethod
    def _success_rate(attempts: list[bool]) -> float | None:
        return sum(attempts) / len(attempts) if attempts else None
