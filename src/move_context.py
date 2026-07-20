"""Extract concrete, non-LLM chess facts from an analyzed move."""

import chess

from src.models import MoveAnalysis, MoveContext


PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
MINOR_STARTING_SQUARES = {chess.B1, chess.G1, chess.C1, chess.F1, chess.B8, chess.G8, chess.C8, chess.F8}
CENTER_SQUARES = {chess.D4, chess.E4, chess.D5, chess.E5}


class MoveContextAnalyzer:
    """Describe only facts provable from the board before and after a move."""

    def analyze(self, analysis: MoveAnalysis) -> MoveContext:
        board = chess.Board(analysis.fen_before)
        move = chess.Move.from_uci(analysis.played_move)
        piece = board.piece_at(move.from_square)
        if piece is None or move not in board.legal_moves:
            raise ValueError("Move context requires a legal move and matching FEN.")

        piece_name = PIECE_NAMES[piece.piece_type]
        from_name = chess.square_name(move.from_square)
        to_name = chess.square_name(move.to_square)
        facts: list[str] = []
        captured = self._captured_piece(board, move)
        is_castling = board.is_castling(move)

        if captured is not None:
            facts.append(
                f"The {piece_name} captured the opponent's "
                f"{PIECE_NAMES[captured.piece_type]} on {to_name}."
            )
        if is_castling:
            side = "kingside" if chess.square_file(move.to_square) == 6 else "queenside"
            facts.append(f"The move castled {side}, moving the king toward safety.")
        if (
            piece.piece_type in {chess.KNIGHT, chess.BISHOP}
            and move.from_square in MINOR_STARTING_SQUARES
        ):
            facts.append(
                f"The {piece_name} developed from its starting square to {to_name}."
            )
        if move.to_square in CENTER_SQUARES:
            facts.append(
                f"The {piece_name} moved to the central square {to_name}."
            )
        if move.promotion is not None:
            facts.append(
                f"The pawn promoted to a {PIECE_NAMES[move.promotion]} on {to_name}."
            )

        board.push(move)
        if board.is_check():
            facts.append("The move gave check.")
        if piece.piece_type != chess.KING:
            attacked = bool(board.attackers(not piece.color, move.to_square))
            defended = bool(board.attackers(piece.color, move.to_square))
            if attacked and not defended:
                facts.append(
                    f"The {piece_name} on {to_name} is attacked and has no defender."
                )

        target = self._most_valuable_target(board, move.to_square, piece.color)
        if target is not None:
            target_square, target_piece = target
            facts.append(
                f"From {to_name}, the {piece_name} attacks the opponent's "
                f"{PIECE_NAMES[target_piece.piece_type]} on "
                f"{chess.square_name(target_square)}."
            )
        if not facts:
            facts.append(f"The {piece_name} moved from {from_name} to {to_name}.")
        return MoveContext(piece_name, from_name, to_name, tuple(facts))

    @staticmethod
    def _captured_piece(board: chess.Board, move: chess.Move) -> chess.Piece | None:
        if not board.is_capture(move):
            return None
        if board.is_en_passant(move):
            square = chess.square(
                chess.square_file(move.to_square),
                chess.square_rank(move.from_square),
            )
            return board.piece_at(square)
        return board.piece_at(move.to_square)

    @staticmethod
    def _most_valuable_target(
        board: chess.Board, square: chess.Square, player_color: chess.Color
    ) -> tuple[chess.Square, chess.Piece] | None:
        piece = board.piece_at(square)
        if piece is None:
            return None
        targets = []
        for target_square in board.attacks(square):
            target = board.piece_at(target_square)
            if target is not None and target.color != player_color and target.piece_type != chess.KING:
                targets.append((target_square, target))
        return max(targets, key=lambda item: PIECE_VALUES[item[1].piece_type], default=None)
