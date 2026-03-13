from __future__ import annotations

from app.logic.board import Board, Piece, PieceType, Color


def is_valid_move(board: Board, piece: Piece, to_row: int, to_col: int) -> bool:
    """Check if moving *piece* to (to_row, to_col) is a legal chess move.

    Does NOT check cooldowns — that is handled at the game layer.
    """
    if not (0 <= to_row <= 7 and 0 <= to_col <= 7):
        return False

    if to_row == piece.row and to_col == piece.col:
        return False

    target = board.piece_at(to_row, to_col)

    # Cannot capture own piece
    if target and target.color == piece.color:
        return False

    dr = to_row - piece.row
    dc = to_col - piece.col

    match piece.piece_type:
        case PieceType.PAWN:
            return _valid_pawn_move(board, piece, to_row, to_col, target)
        case PieceType.KNIGHT:
            return _valid_knight_move(dr, dc)
        case PieceType.BISHOP:
            return _valid_bishop_move(board, piece, dr, dc)
        case PieceType.ROOK:
            return _valid_rook_move(board, piece, dr, dc)
        case PieceType.QUEEN:
            return _valid_bishop_move(board, piece, dr, dc) or _valid_rook_move(board, piece, dr, dc)
        case PieceType.KING:
            return _valid_king_move(dr, dc)

    return False


def _valid_pawn_move(
    board: Board, piece: Piece, to_row: int, to_col: int, target: Piece | None
) -> bool:
    direction = 1 if piece.color == Color.WHITE else -1
    start_row = 1 if piece.color == Color.WHITE else 6
    dr = to_row - piece.row
    dc = to_col - piece.col

    # Forward one square
    if dc == 0 and dr == direction and target is None:
        return True

    # Forward two squares from start
    if dc == 0 and dr == 2 * direction and piece.row == start_row and target is None:
        intermediate = board.piece_at(piece.row + direction, piece.col)
        if intermediate is None:
            return True

    # Diagonal capture
    if abs(dc) == 1 and dr == direction and target is not None:
        return True

    return False


def _valid_knight_move(dr: int, dc: int) -> bool:
    return (abs(dr), abs(dc)) in ((2, 1), (1, 2))


def _valid_bishop_move(board: Board, piece: Piece, dr: int, dc: int) -> bool:
    if abs(dr) != abs(dc) or dr == 0:
        return False
    return _path_clear(board, piece, dr, dc)


def _valid_rook_move(board: Board, piece: Piece, dr: int, dc: int) -> bool:
    if dr != 0 and dc != 0:
        return False
    if dr == 0 and dc == 0:
        return False
    return _path_clear(board, piece, dr, dc)


def _valid_king_move(dr: int, dc: int) -> bool:
    return abs(dr) <= 1 and abs(dc) <= 1


def _path_clear(board: Board, piece: Piece, dr: int, dc: int) -> bool:
    """Check that the path between piece and destination is clear (exclusive)."""
    step_r = (1 if dr > 0 else -1) if dr != 0 else 0
    step_c = (1 if dc > 0 else -1) if dc != 0 else 0
    steps = max(abs(dr), abs(dc))

    for i in range(1, steps):
        r = piece.row + step_r * i
        c = piece.col + step_c * i
        if board.piece_at(r, c) is not None:
            return False
    return True
