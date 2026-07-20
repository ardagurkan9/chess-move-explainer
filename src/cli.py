"""Terminal user interface for playing an analyzed game against Stockfish."""

from collections.abc import Callable
from typing import Protocol

import chess

from src.analysis import AnalysisError, MoveAnalyzer, PositionAnalyzer
from src.commentary import CommentaryGenerator, CommentaryService
from src.game import ChessGame, MoveError
from src.models import (
    AnalyzedMove,
    CommentaryResult,
    EngineResult,
    GameReport,
    MoveAnalysis,
    MoveClassification,
    MoveQuality,
    ThemeDetection,
    UserLevel,
)
from src.mistake_detector import MistakeDetector
from src.move_classifier import MoveClassifier
from src.report import GameReportBuilder
from src.services.history_service import HistoryService
from src.services.practice_service import PracticeMoveError, PracticeService
from src.services.progress_service import ProgressService

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


class ConfigurableOpponent(PositionAnalyzer, Protocol):
    """Engine interface required for an Elo-limited opponent."""

    def elo_range(self) -> tuple[int, int]: ...

    def configure_strength(self, elo: int) -> None: ...


class TerminalGame:
    """Run a complete terminal game between a user and Stockfish."""

    def __init__(
        self,
        engine: PositionAnalyzer,
        *,
        depth: int = 12,
        input_fn: InputFunction = input,
        output_fn: OutputFunction = print,
        game_factory: Callable[[], ChessGame] = ChessGame,
        commentary: CommentaryGenerator | None = None,
        history_service: HistoryService | None = None,
        opponent_engine: ConfigurableOpponent | None = None,
    ) -> None:
        self.engine = engine
        self.depth = depth
        self.input = input_fn
        self.output = output_fn
        self.game_factory = game_factory
        self.move_analyzer = MoveAnalyzer(engine)
        self.classifier = MoveClassifier()
        self.mistake_detector = MistakeDetector()
        self.commentary = commentary or CommentaryService()
        self.history_service = history_service
        self.opponent_engine = opponent_engine
        self.user_level = UserLevel.BEGINNER
        self.report_builder = GameReportBuilder()
        self.analyzed_moves: list[AnalyzedMove] = []

    def run(self) -> str | None:
        """Run the game loop and return its result, or ``None`` if the user quits."""
        self._show_welcome()
        player_color = self._choose_color()
        self.user_level = self._choose_level()
        if self.opponent_engine is not None:
            self._choose_opponent_elo()
        game = self.game_factory()
        self.analyzed_moves = []

        while not game.is_game_over:
            self._show_board(game)
            if game.turn == player_color:
                if not self._play_user_turn(game):
                    self.output("Game stopped by the user.")
                    return None
            else:
                self._play_engine_turn(game)

        self._show_board(game)
        result = game.result
        self.output(f"Game over: {self._result_message(game)}")
        self.output(f"Moves: {' '.join(game.uci_history)}")
        report = self.report_builder.build(
            game, self.analyzed_moves, player_color=player_color
        )
        self._show_report(report)
        self._save_history(report)
        return result

    def _choose_color(self) -> chess.Color:
        while True:
            choice = self.input("Choose your color [w/b]: ").strip().lower()
            if choice in {"w", "white"}:
                return chess.WHITE
            if choice in {"b", "black"}:
                return chess.BLACK
            self.output("Please enter 'w' for White or 'b' for Black.")

    def _play_user_turn(self, game: ChessGame) -> bool:
        while True:
            move_text = self.input("Your move (UCI, or 'quit'): ").strip()
            if move_text.lower() in {"quit", "exit", "q"}:
                return False

            try:
                move = chess.Move.from_uci(move_text.lower())
                analysis = self.move_analyzer.analyze_move(
                    game.board, move, depth=self.depth
                )
                game.play_uci(move.uci())
            except (
                AnalysisError,
                MoveError,
                chess.InvalidMoveError,
                ValueError,
            ) as error:
                self.output(f"Invalid move: {error}")
                continue

            classification = self.classifier.classify(analysis)
            theme_detection = (
                self.mistake_detector.detect(analysis, classification)
                if classification.quality
                in {
                    MoveQuality.INACCURACY,
                    MoveQuality.MISTAKE,
                    MoveQuality.BLUNDER,
                }
                else None
            )
            commentary = self._show_analysis(
                analysis, classification, theme_detection
            )
            self.analyzed_moves.append(
                AnalyzedMove(
                    analysis,
                    classification,
                    theme_detection,
                    commentary,
                )
            )
            return True

    def _choose_level(self) -> UserLevel:
        options = {
            "1": UserLevel.BEGINNER,
            "beginner": UserLevel.BEGINNER,
            "2": UserLevel.INTERMEDIATE,
            "intermediate": UserLevel.INTERMEDIATE,
            "3": UserLevel.ADVANCED,
            "advanced": UserLevel.ADVANCED,
        }
        while True:
            choice = self.input(
                "Choose explanation level [1=Beginner, 2=Intermediate, 3=Advanced]: "
            ).strip().lower()
            if choice in options:
                return options[choice]
            self.output("Please enter 1, 2, or 3.")

    def _play_engine_turn(self, game: ChessGame) -> None:
        opponent = self.opponent_engine or self.engine
        result = opponent.analyze(game.board, depth=self.depth)
        game.play_uci(result.best_move)
        self.output(f"Stockfish plays: {result.best_move}")

    def _choose_opponent_elo(self) -> int:
        assert self.opponent_engine is not None
        minimum, maximum = self.opponent_engine.elo_range()
        while True:
            raw_value = self.input(
                f"Choose opponent Elo [{minimum}-{maximum}]: "
            ).strip()
            try:
                elo = int(raw_value)
                self.opponent_engine.configure_strength(elo)
            except ValueError:
                self.output(f"Please enter an Elo between {minimum} and {maximum}.")
                continue
            self.output(f"Opponent strength set to approximately {elo} Elo.")
            return elo

    def _show_welcome(self) -> None:
        self.output("Chess Improvement Coach")
        self.output("Enter moves in UCI notation, for example: e2e4")

    def _show_board(self, game: ChessGame) -> None:
        self.output("")
        self.output(self._format_board(game.board))
        side = "White" if game.turn == chess.WHITE else "Black"
        self.output(f"Turn: {side}")

    @staticmethod
    def _format_board(board: chess.Board) -> str:
        """Return an ASCII board with file and rank coordinates."""
        file_labels = "  a b c d e f g h"
        rows = [file_labels]
        for rank in range(7, -1, -1):
            rank_label = str(rank + 1)
            pieces = []
            for file_index in range(8):
                piece = board.piece_at(chess.square(file_index, rank))
                pieces.append(piece.symbol() if piece else ".")
            rows.append(f"{rank_label} {' '.join(pieces)} {rank_label}")
        rows.append(file_labels)
        return "\n".join(rows)

    def _show_analysis(
        self,
        analysis: MoveAnalysis,
        classification: MoveClassification,
        theme_detection: ThemeDetection | None,
    ) -> CommentaryResult:
        self.output(
            f"Analysis: {classification.quality.value} - {classification.reason}"
        )
        self.output(f"Stockfish's choice: {analysis.best_move}")
        self.output(
            "Evaluation: "
            f"{self._format_score(analysis.before)} -> "
            f"{self._format_score(analysis.after)}"
        )
        if analysis.before.pv:
            self.output(f"Suggested line: {' '.join(analysis.before.pv)}")
        if theme_detection is not None:
            self.output(
                "Theme: "
                f"{theme_detection.theme.value} "
                f"({theme_detection.confidence:.0%} confidence)"
            )
        explanation = self.commentary.generate(
            analysis,
            classification,
            level=self.user_level,
            theme_detection=theme_detection,
        )
        self.output(f"Coach: {explanation.text}")
        return explanation

    def _save_history(self, report: GameReport) -> None:
        """Persist a completed game without making gameplay depend on the database."""
        if self.history_service is None:
            return
        try:
            game_id = self.history_service.save_completed_game(
                report,
                self.analyzed_moves,
                level=self.user_level,
            )
            summaries = self.history_service.recurring_mistakes()
        except Exception as error:
            self.output(
                "Game history could not be saved "
                f"({type(error).__name__})."
            )
            return

        self.output(f"Game history saved with ID {game_id}.")
        if summaries:
            recurring = ", ".join(
                f"{summary.theme.value}: {summary.count}" for summary in summaries
            )
            self.output(f"Recurring mistakes: {recurring}")

    @staticmethod
    def _format_score(result: EngineResult) -> str:
        score_cp = result.score_cp
        mate = result.mate
        if mate is not None:
            return f"Mate {mate:+d}"
        if score_cp is None:
            return "unknown"
        return f"{score_cp / 100:+.2f}"

    @staticmethod
    def _result_message(game: ChessGame) -> str:
        if game.is_checkmate:
            winner = "Black" if game.turn == chess.WHITE else "White"
            return f"{winner} wins by checkmate ({game.result})"
        if game.is_stalemate:
            return f"Draw by stalemate ({game.result})"
        return f"Draw ({game.result})"

    def _show_report(self, report: GameReport) -> None:
        self.output("")
        self.output("=== Game Report ===")
        self.output(f"Result: {report.result}")
        self.output(f"User moves analyzed: {report.total_user_moves}")
        average = (
            f"{report.average_centipawn_loss:.2f}"
            if report.average_centipawn_loss is not None
            else "N/A"
        )
        self.output(f"Average centipawn loss: {average}")
        distribution = ", ".join(
            f"{quality.value}: {report.quality_counts[quality]}"
            for quality in MoveQuality
        )
        self.output(f"Move quality: {distribution}")
        themes = ", ".join(
            f"{theme.value}: {count}"
            for theme, count in report.theme_counts.items()
            if count
        )
        self.output(f"Mistake themes: {themes or 'None'}")
        self.output(f"Missed mates: {report.missed_mates}")
        self.output(f"Allowed mates: {report.allowed_mates}")
        if report.biggest_error is not None:
            record = report.biggest_error
            self.output(
                "Biggest error: "
                f"{record.analysis.played_move} "
                f"({record.classification.quality.value})"
            )
        self.output("Improvement areas:")
        for area in report.improvement_areas:
            self.output(f"- {area}")
        self.output("")
        self.output("=== PGN ===")
        self.output(report.pgn)


class TerminalApplication:
    """Choose between a Stockfish game and review of saved mistakes."""

    def __init__(
        self,
        game: TerminalGame,
        *,
        practice_service: PracticeService | None = None,
        progress_service: ProgressService | None = None,
    ) -> None:
        self.game = game
        self.practice_service = practice_service
        self.progress_service = progress_service
        self.input = game.input
        self.output = game.output

    def run(self) -> str | None:
        """Run the selected terminal workflow."""
        while True:
            self.output("Chess Improvement Coach")
            self.output("1. Play against Stockfish")
            self.output("2. Review past mistakes")
            self.output("3. View progress")
            choice = self.input(
                "Choose an option [1/2/3, or 'quit']: "
            ).strip().lower()
            if choice in {"1", "play"}:
                return self.game.run()
            if choice in {"2", "review", "practice"}:
                self._run_practice()
                return None
            if choice in {"3", "progress"}:
                self._show_progress()
                return None
            if choice in {"quit", "exit", "q"}:
                return None
            self.output("Please enter 1, 2, 3, or 'quit'.")

    def _show_progress(self) -> None:
        if self.progress_service is None:
            self.output("Progress reporting requires a configured database.")
            return
        try:
            summary = self.progress_service.summary()
        except Exception as error:
            self.output(
                "Progress could not be loaded "
                f"({type(error).__name__})."
            )
            return

        self.output("")
        self.output("=== Personal Progress ===")
        self.output(f"Completed games: {summary.total_games}")
        self.output(f"Analyzed moves: {summary.total_analyzed_moves}")
        self.output(f"Detected mistakes: {summary.total_mistakes}")
        common = summary.most_common_mistake
        self.output(
            "Most common mistake: "
            + (f"{common.theme.value} ({common.count})" if common else "None")
        )
        if summary.mistake_counts:
            themes = ", ".join(
                f"{item.theme.value}: {item.count}"
                for item in summary.mistake_counts
            )
            self.output(f"Mistake themes: {themes}")
        self.output(
            "Practice positions: "
            f"pending={summary.pending_positions}, "
            f"learning={summary.learning_positions}, "
            f"mastered={summary.mastered_positions}"
        )
        self.output(f"Due now: {summary.due_positions}")
        self.output(f"Practice attempts: {summary.total_practice_attempts}")
        self.output(
            f"Correct answers: {summary.correct_practice_attempts}"
        )
        self.output(
            "Success rate: "
            + self._format_percentage(summary.success_rate)
        )
        self.output(
            "Recent success rate (last 10): "
            + self._format_percentage(summary.recent_success_rate)
        )
        change = summary.success_rate_change
        self.output(
            "Recent change: "
            + (
                f"{change * 100:+.1f} percentage points"
                if change is not None
                else "Not enough data (20 attempts required)"
            )
        )
        if summary.due_positions:
            next_review = "Available now"
        elif summary.next_review_at is not None:
            next_review = f"{summary.next_review_at:%Y-%m-%d %H:%M UTC}"
        else:
            next_review = "No review scheduled"
        self.output(f"Next review: {next_review}")

    @staticmethod
    def _format_percentage(value: float | None) -> str:
        return f"{value:.1%}" if value is not None else "N/A"

    def _run_practice(self) -> None:
        if self.practice_service is None:
            self.output("Practice requires a configured database.")
            return
        level = self.game._choose_level()

        while True:
            try:
                position = self.practice_service.next_position()
            except Exception as error:
                self.output(
                    "Practice positions could not be loaded "
                    f"({type(error).__name__})."
                )
                return
            if position is None:
                self.output("No practice positions are due right now.")
                return

            board = chess.Board(position.fen)
            self.output("")
            self.output("=== Practice Position ===")
            self.output(TerminalGame._format_board(board))
            self.output(f"Theme: {position.theme.value}")
            self.output(f"Previous attempts: {position.attempts}")

            while True:
                move_text = self.input(
                    "Find the best move (UCI, or 'quit'): "
                ).strip()
                if move_text.lower() in {"quit", "exit", "q"}:
                    return
                try:
                    result = self.practice_service.submit(
                        position,
                        move_text,
                        level=level,
                    )
                except PracticeMoveError as error:
                    self.output(f"Invalid move: {error}")
                    continue
                except Exception as error:
                    self.output(
                        "Practice answer could not be saved "
                        f"({type(error).__name__})."
                    )
                    return
                break

            if result.correct:
                self.output(f"Correct! {result.best_move} is the stored best move.")
            else:
                self.output(
                    f"Not quite. The stored best move was {result.best_move}."
                )
                if result.classification is not None:
                    self.output(
                        "Analysis: "
                        f"{result.classification.quality.value} - "
                        f"{result.classification.reason}"
                    )
                if result.theme_detection is not None:
                    self.output(f"Theme: {result.theme_detection.theme.value}")
                if result.commentary is not None:
                    self.output(f"Coach: {result.commentary.text}")
            self.output(
                "Next review: "
                f"{result.updated_position.next_review_at:%Y-%m-%d %H:%M UTC}"
            )
