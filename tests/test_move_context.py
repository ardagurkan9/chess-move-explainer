import chess

from src.models import EngineResult, MoveAnalysis
from src.move_context import MoveContextAnalyzer


def analysis_for(fen: str, move_uci: str) -> MoveAnalysis:
    board = chess.Board(fen)
    board.push_uci(move_uci)
    result = EngineResult(None, 0, None, (), 12)
    return MoveAnalysis(
        played_move=move_uci,
        player_is_white=chess.Board(fen).turn,
        fen_before=fen,
        fen_after=board.fen(),
        before=result,
        after=result,
        centipawn_loss=0,
        missed_forced_mate=False,
        allowed_forced_mate=False,
    )


def test_describes_a_central_pawn_move() -> None:
    context = MoveContextAnalyzer().analyze(
        analysis_for(chess.STARTING_FEN, "e2e4")
    )

    assert context.piece == "pawn"
    assert context.from_square == "e2"
    assert context.to_square == "e4"
    assert "The pawn moved to the central square e4." in context.facts


def test_describes_minor_piece_development() -> None:
    context = MoveContextAnalyzer().analyze(
        analysis_for(chess.STARTING_FEN, "g1f3")
    )

    assert "The knight developed from its starting square to f3." in context.facts


def test_describes_castling() -> None:
    context = MoveContextAnalyzer().analyze(
        analysis_for("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1")
    )

    assert "The move castled kingside, moving the king toward safety." in context.facts


def test_describes_a_capture_without_guessing_a_plan() -> None:
    context = MoveContextAnalyzer().analyze(
        analysis_for("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "e4d5")
    )

    assert "The pawn captured the opponent's pawn on d5." in context.facts
    assert all("plan" not in fact.lower() for fact in context.facts)
