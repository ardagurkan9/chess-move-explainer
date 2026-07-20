import chess
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from src.database import Database
from src.db_models import Base, PracticeAttemptRecord
from src.models import (
    AnalyzedMove,
    CommentaryResult,
    EngineResult,
    GameReport,
    MistakeTheme,
    MoveAnalysis,
    MoveClassification,
    MoveQuality,
    ThemeDetection,
    UserLevel,
)
from src.repositories.sqlalchemy_repository import SQLAlchemyGameHistoryRepository


def analyzed_blunder() -> AnalyzedMove:
    board = chess.Board()
    before_fen = board.fen()
    board.push_uci("f2f3")
    return AnalyzedMove(
        analysis=MoveAnalysis(
            played_move="f2f3",
            player_is_white=True,
            fen_before=before_fen,
            fen_after=board.fen(),
            before=EngineResult("e2e4", 30, None, ("e2e4", "e7e5"), 12),
            after=EngineResult("e7e5", -320, None, ("e7e5",), 12),
            centipawn_loss=350,
        ),
        classification=MoveClassification(
            MoveQuality.BLUNDER, "Large evaluation loss.", 350
        ),
        theme_detection=ThemeDetection(
            MistakeTheme.KING_SAFETY,
            ("The move weakens the king.",),
            0.85,
        ),
        commentary=CommentaryResult(
            "Keep the king shelter intact.",
            UserLevel.BEGINNER,
            source="gemini",
        ),
    )


def report() -> GameReport:
    counts = {quality: 0 for quality in MoveQuality}
    counts[MoveQuality.BLUNDER] = 1
    themes = {theme: 0 for theme in MistakeTheme}
    themes[MistakeTheme.KING_SAFETY] = 1
    move = analyzed_blunder()
    return GameReport(
        result="0-1",
        player_is_white=True,
        total_user_moves=1,
        average_centipawn_loss=350.0,
        quality_counts=counts,
        theme_counts=themes,
        missed_mates=0,
        allowed_mates=0,
        biggest_error=move,
        improvement_areas=("Protect the king.",),
        pgn="1. f3 e5 0-1",
    )


def test_repository_saves_history_and_counts_recurring_mistakes() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine)
    repository = SQLAlchemyGameHistoryRepository(database)

    first_id = repository.save_game(
        username="student",
        level=UserLevel.BEGINNER,
        report=report(),
        analyzed_moves=(analyzed_blunder(),),
    )
    second_id = repository.save_game(
        username="student",
        level=UserLevel.INTERMEDIATE,
        report=report(),
        analyzed_moves=(analyzed_blunder(),),
    )
    summaries = repository.recurring_mistakes(username="student")

    assert first_id != second_id
    assert len(summaries) == 1
    assert summaries[0].theme is MistakeTheme.KING_SAFETY
    assert summaries[0].count == 2
    database.close()


def test_repository_loads_and_updates_a_due_practice_position() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine)
    repository = SQLAlchemyGameHistoryRepository(database)
    repository.save_game(
        username="student",
        level=UserLevel.BEGINNER,
        report=report(),
        analyzed_moves=(analyzed_blunder(),),
    )
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

    due = repository.due_practice_position(username="student", as_of=now)
    games = repository.practice_games(username="student", as_of=now)

    assert due is not None
    assert len(games) == 1
    assert games[0].id == due.game_id
    assert games[0].mistake_count == 1
    assert games[0].due_count == 1
    positions = repository.practice_positions_for_game(
        username="student", game_id=games[0].id, as_of=now
    )
    assert len(positions) == 1
    assert positions[0].played_move == "f2f3"
    assert positions[0].ply_number == 1
    assert due.fen == analyzed_blunder().analysis.fen_before
    assert due.solution_moves[0] == "e2e4"
    updated = repository.record_practice_attempt(
        username="student",
        position_id=due.id,
        attempted_move="e2e4",
        correct=True,
        quality=None,
        detected_theme=None,
        commentary=None,
        commentary_source=None,
        status="learning",
        solved=True,
        next_review_at=now + timedelta(days=1),
    )
    assert updated.attempts == 1
    assert updated.successful_attempts == 1
    assert repository.due_practice_position(username="student", as_of=now) is None
    progress = repository.progress_summary(username="student", as_of=now)
    assert progress.total_games == 1
    assert progress.total_analyzed_moves == 1
    assert progress.total_mistakes == 1
    assert progress.most_common_mistake is not None
    assert progress.most_common_mistake.theme is MistakeTheme.KING_SAFETY
    assert progress.pending_positions == 0
    assert progress.learning_positions == 1
    assert progress.mastered_positions == 0
    assert progress.total_practice_attempts == 1
    assert progress.correct_practice_attempts == 1
    assert progress.success_rate == 1.0
    assert progress.recent_success_rate == 1.0
    assert progress.success_rate_change is None
    assert progress.next_review_at is not None
    with database.session() as session:
        attempt = session.scalar(select(PracticeAttemptRecord))
        assert attempt is not None
        assert attempt.attempted_move == "e2e4"
        assert attempt.correct is True
        assert attempt.scheduled_review_at.replace(tzinfo=timezone.utc) == (
            now + timedelta(days=1)
        )
    database.close()


def test_progress_summary_is_empty_for_an_unknown_user() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine)
    repository = SQLAlchemyGameHistoryRepository(database)

    progress = repository.progress_summary(
        username="unknown",
        as_of=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )

    assert progress.total_games == 0
    assert progress.total_analyzed_moves == 0
    assert progress.total_mistakes == 0
    assert progress.mistake_counts == ()
    assert progress.total_practice_attempts == 0
    assert progress.success_rate is None
    assert progress.next_review_at is None
    database.close()
