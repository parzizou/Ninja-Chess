from __future__ import annotations

import time

from app.logic.board import Board, Piece, PieceType, Color


def is_valid_move(board: Board, piece: Piece, to_row: int, to_col: int) -> bool:
    """Check if moving *piece* to (to_row, to_col) is legal. Does NOT check cooldowns."""
    if not (0 <= to_row <= 7 and 0 <= to_col <= 7):
        return False
    if to_row == piece.row and to_col == piece.col:
        return False

    target = board.piece_at(to_row, to_col)
    if target and target.color == piece.color:
        return False

    dr = to_row - piece.row
    dc = to_col - piece.col

    match piece.piece_type:
        case PieceType.PAWN:
            return _valid_pawn_move(board, piece, to_row, to_col, target, dr, dc)
        case PieceType.KNIGHT:
            return (abs(dr), abs(dc)) in ((2, 1), (1, 2))
        case PieceType.BISHOP:
            return _valid_bishop_move(board, piece, dr, dc)
        case PieceType.ROOK:
            return _valid_rook_move(board, piece, dr, dc)
        case PieceType.QUEEN:
            return _valid_bishop_move(board, piece, dr, dc) or _valid_rook_move(board, piece, dr, dc)
        case PieceType.KING:
            return _valid_king_move(board, piece, dr, dc)

    return False


def is_in_check(board: Board, color: Color) -> bool:
    """Return True if the king of *color* is currently attacked by any opponent piece."""
    king = board.king(color)
    if not king:
        return False
    opponent = Color.BLACK if color == Color.WHITE else Color.WHITE
    for p in board.pieces:
        if p.alive and p.color == opponent:
            if _can_attack(board, p, king.row, king.col):
                return True
    return False


# ── Internal helpers ─────────────────────────────────────────────────────────

def _can_attack(board: Board, piece: Piece, to_row: int, to_col: int) -> bool:
    """Check if *piece* can attack a square — no castling, no en-passant.
    Used for check detection to avoid recursion."""
    if not (0 <= to_row <= 7 and 0 <= to_col <= 7):
        return False
    if to_row == piece.row and to_col == piece.col:
        return False
    target = board.piece_at(to_row, to_col)
    if target and target.color == piece.color:
        return False
    dr = to_row - piece.row
    dc = to_col - piece.col
    match piece.piece_type:
        case PieceType.PAWN:
            direction = 1 if piece.color == Color.WHITE else -1
            return abs(dc) == 1 and dr == direction
        case PieceType.KNIGHT:
            return (abs(dr), abs(dc)) in ((2, 1), (1, 2))
        case PieceType.BISHOP:
            return _valid_bishop_move(board, piece, dr, dc)
        case PieceType.ROOK:
            return _valid_rook_move(board, piece, dr, dc)
        case PieceType.QUEEN:
            return _valid_bishop_move(board, piece, dr, dc) or _valid_rook_move(board, piece, dr, dc)
        case PieceType.KING:
            return abs(dr) <= 1 and abs(dc) <= 1
    return False


def _valid_pawn_move(
    board: Board, piece: Piece, to_row: int, to_col: int,
    target: Piece | None, dr: int, dc: int,
) -> bool:
    direction = 1 if piece.color == Color.WHITE else -1
    start_row = 1 if piece.color == Color.WHITE else 6

    # Forward one square
    if dc == 0 and dr == direction and target is None:
        return True

    # Forward two squares from start
    if dc == 0 and dr == 2 * direction and piece.row == start_row and target is None:
        if board.piece_at(piece.row + direction, piece.col) is None:
            return True

    # Normal diagonal capture
    if abs(dc) == 1 and dr == direction and target is not None:
        return True

    # En passant
    if (abs(dc) == 1 and dr == direction and target is None
            and board.en_passant_square is not None
            and board.en_passant_square == (to_row, to_col)
            and board.en_passant_expires > time.time()):
        return True

    return False


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


def _valid_king_move(board: Board, piece: Piece, dr: int, dc: int) -> bool:
    # Normal one-square move
    if abs(dr) <= 1 and abs(dc) <= 1:
        return True
    # Castling: king moves exactly 2 squares horizontally
    if dr == 0 and abs(dc) == 2:
        return _valid_castling(board, piece, dc)
    return False


def _valid_castling(board: Board, piece: Piece, dc: int) -> bool:
    """Validate castling: king and rook must not have moved, path must be clear,
    king must not currently be in check."""
    if piece.last_move_time != 0.0:
        return False

    if dc == 2:       # Kingside
        rook_col = 7
        path_cols = [5, 6]
    else:             # Queenside
        rook_col = 0
        path_cols = [1, 2, 3]

    rook = board.piece_at(piece.row, rook_col)
    if rook is None or rook.piece_type != PieceType.ROOK or rook.color != piece.color:
        return False
    if rook.last_move_time != 0.0:
        return False

    for col in path_cols:
        if board.piece_at(piece.row, col) is not None:
            return False

    # King must not be in check (uses _can_attack to avoid recursion)
    if is_in_check(board, piece.color):
        return False

    return True


def _path_clear(board: Board, piece: Piece, dr: int, dc: int) -> bool:
    step_r = (1 if dr > 0 else -1) if dr != 0 else 0
    step_c = (1 if dc > 0 else -1) if dc != 0 else 0
    steps = max(abs(dr), abs(dc))
    for i in range(1, steps):
        if board.piece_at(piece.row + step_r * i, piece.col + step_c * i) is not None:
            return False
    return True
