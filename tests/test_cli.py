import chess
from unittest.mock import MagicMock

from src.cli import TerminalApplication, TerminalGame
from src.models import (
    EngineResult,
    MoveAnalysis,
    MoveClassification,
    MoveQuality,
    UserLevel,
)


class ScriptedEngine:
    """Deterministic engine that permits a complete Fool's Mate test game."""

    def analyze(
        self,
        position: chess.Board | str,
        *,
        depth: int | None = 12,
        time_limit: float | None = None,
    ) -> EngineResult:
        board = position if isinstance(position, chess.Board) else chess.Board(position)
        history = tuple(move.uci() for move in board.move_stack)
        if history == ("f2f3",):
            best_move = "e7e5"
        elif history == ("f2f3", "e7e5", "g2g4"):
            best_move = "d8h4"
        else:
            best_move = next(iter(board.legal_moves)).uci()
        return EngineResult(
            best_move=best_move,
            score_cp=0,
            mate=None,
            pv=(best_move,),
            depth=depth,
        )


class ConfigurableScriptedEngine(ScriptedEngine):
    def __init__(self) -> None:
        self.configured_elo: int | None = None

    def elo_range(self) -> tuple[int, int]:
        return 1320, 3190

    def configure_strength(self, elo: int) -> None:
        if not 1320 <= elo <= 3190:
            raise ValueError("unsupported Elo")
        self.configured_elo = elo


def scripted_input(*answers: str):
    iterator = iter(answers)
    return lambda _prompt: next(iterator)


def test_complete_terminal_game_reaches_checkmate() -> None:
    output: list[str] = []
    history_service = MagicMock()
    history_service.save_completed_game.return_value = 17
    history_service.recurring_mistakes.return_value = ()
    game = TerminalGame(
        ScriptedEngine(),
        input_fn=scripted_input("w", "1", "f2f3", "g2g4"),
        output_fn=output.append,
        history_service=history_service,
    )

    result = game.run()

    assert result == "0-1"
    assert "Stockfish plays: e7e5" in output
    assert "Stockfish plays: d8h4" in output
    assert any("Black wins by checkmate" in line for line in output)
    assert any("f2f3 e7e5 g2g4 d8h4" in line for line in output)
    assert "=== Game Report ===" in output
    assert "User moves analyzed: 2" in output
    assert "=== PGN ===" in output
    assert any("1. f3 e5 2. g4 Qh4# 0-1" in line for line in output)
    assert "Game history saved with ID 17." in output
    history_service.save_completed_game.assert_called_once()


def test_invalid_color_and_move_are_retried() -> None:
    output: list[str] = []
    game = TerminalGame(
        ScriptedEngine(),
        input_fn=scripted_input(
            "green", "white", "4", "2", "bad move", "e2e5", "e2e4", "quit"
        ),
        output_fn=output.append,
    )

    result = game.run()

    assert result is None
    assert any("Please enter" in line for line in output)
    assert sum("Invalid move" in line for line in output) == 2
    assert any("Analysis:" in line for line in output)
    assert any("Coach [Template]:" in line for line in output)


def test_choosing_black_makes_stockfish_play_first() -> None:
    output: list[str] = []
    game = TerminalGame(
        ScriptedEngine(),
        input_fn=scripted_input("b", "3", "quit"),
        output_fn=output.append,
    )

    result = game.run()

    assert result is None
    assert any(line.startswith("Stockfish plays:") for line in output)


def test_board_display_contains_file_and_rank_coordinates() -> None:
    rendered = TerminalGame._format_board(chess.Board())
    lines = rendered.splitlines()

    assert lines[0] == "  a b c d e f g h"
    assert lines[1] == "8 r n b q k b n r 8"
    assert lines[-2] == "1 R N B Q K B N R 1"
    assert lines[-1] == "  a b c d e f g h"


def test_good_move_output_does_not_show_a_mistake_theme() -> None:
    output: list[str] = []
    game = TerminalGame(ScriptedEngine(), output_fn=output.append)
    game.user_level = UserLevel.INTERMEDIATE
    analysis = MoveAnalysis(
        played_move="b1c3",
        player_is_white=True,
        fen_before=chess.STARTING_FEN,
        fen_after=chess.STARTING_FEN,
        before=EngineResult("d2d4", 35, None, ("d2d4",), 12),
        after=EngineResult("d7d5", 38, None, ("d7d5",), 12),
        centipawn_loss=0,
        missed_forced_mate=False,
        allowed_forced_mate=False,
    )

    game._show_analysis(
        analysis,
        MoveClassification(MoveQuality.BEST, "Top evaluation.", 0),
        None,
    )

    assert not any(line.startswith("Theme:") for line in output)


def test_terminal_application_can_open_practice_when_no_position_is_due() -> None:
    output: list[str] = []
    game = TerminalGame(
        ScriptedEngine(),
        input_fn=scripted_input("2", "1"),
        output_fn=output.append,
    )
    practice = MagicMock()
    practice.next_position.return_value = None

    TerminalApplication(game, practice_service=practice).run()

    practice.next_position.assert_called_once()
    assert "No practice positions are due right now." in output


def test_user_selects_opponent_elo_before_play() -> None:
    output: list[str] = []
    opponent = ConfigurableScriptedEngine()
    game = TerminalGame(
        ScriptedEngine(),
        opponent_engine=opponent,
        input_fn=scripted_input("w", "1", "1000", "1800", "quit"),
        output_fn=output.append,
    )

    result = game.run()

    assert result is None
    assert opponent.configured_elo == 1800
    assert "Please enter an Elo between 1320 and 3190." in output
    assert "Opponent strength set to approximately 1800 Elo." in output
