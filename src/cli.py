"""Terminal user interface for playing an analyzed game against Stockfish."""

from collections.abc import Callable

import chess

from src.analysis import AnalysisError, MoveAnalyzer, PositionAnalyzer
from src.commentary import CommentaryGenerator, CommentaryService
from src.game import ChessGame, MoveError
from src.models import EngineResult, MoveAnalysis, MoveClassification, UserLevel
from src.move_classifier import MoveClassifier

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


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
    ) -> None:
        self.engine = engine
        self.depth = depth
        self.input = input_fn
        self.output = output_fn
        self.game_factory = game_factory
        self.move_analyzer = MoveAnalyzer(engine)
        self.classifier = MoveClassifier()
        self.commentary = commentary or CommentaryService()
        self.user_level = UserLevel.BEGINNER

    def run(self) -> str | None:
        """Run the game loop and return its result, or ``None`` if the user quits."""
        self._show_welcome()
        player_color = self._choose_color()
        self.user_level = self._choose_level()
        game = self.game_factory()

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
            self._show_analysis(analysis, classification)
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
        result = self.engine.analyze(game.board, depth=self.depth)
        game.play_uci(result.best_move)
        self.output(f"Stockfish plays: {result.best_move}")

    def _show_welcome(self) -> None:
        self.output("Explainable Chess Coach")
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
        self, analysis: MoveAnalysis, classification: MoveClassification
    ) -> None:
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
        explanation = self.commentary.generate(
            analysis, classification, level=self.user_level
        )
        self.output(f"Coach [{explanation.source.title()}]: {explanation.text}")

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
