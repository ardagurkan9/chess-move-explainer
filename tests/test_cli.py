import chess

from src.cli import TerminalGame
from src.models import EngineResult


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


def scripted_input(*answers: str):
    iterator = iter(answers)
    return lambda _prompt: next(iterator)


def test_complete_terminal_game_reaches_checkmate() -> None:
    output: list[str] = []
    game = TerminalGame(
        ScriptedEngine(),
        input_fn=scripted_input("w", "1", "f2f3", "g2g4"),
        output_fn=output.append,
    )

    result = game.run()

    assert result == "0-1"
    assert "Stockfish plays: e7e5" in output
    assert "Stockfish plays: d8h4" in output
    assert any("Black wins by checkmate" in line for line in output)
    assert any("f2f3 e7e5 g2g4 d8h4" in line for line in output)


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
