from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time


class PieceType(str, Enum):
    PAWN = "pawn"
    KNIGHT = "knight"
    BISHOP = "bishop"
    ROOK = "rook"
    QUEEN = "queen"
    KING = "king"


class Color(str, Enum):
    WHITE = "white"
    BLACK = "black"


# Cooldown in seconds per piece type
COOLDOWNS: dict[PieceType, float] = {
    PieceType.PAWN: 1.5,
    PieceType.KNIGHT: 3.0,
    PieceType.BISHOP: 3.0,
    PieceType.ROOK: 4.0,
    PieceType.QUEEN: 5.0,
    PieceType.KING: 3.0,
}


@dataclass
class Piece:
    piece_type: PieceType
    color: Color
    row: int  # 0-7, 0 = bottom (white side)
    col: int  # 0-7, 0 = left
    alive: bool = True
    last_move_time: float = 0.0
    piece_id: int = 0
    tags: dict[str, Any] = field(default_factory=dict)  # timestamp of last move

    @property
    def cooldown_duration(self) -> float:
        return COOLDOWNS[self.piece_type]

    def is_on_cooldown(self, now: float | None = None) -> bool:
        if self.last_move_time == 0.0:
            return False
        if now is None:
            now = time.time()
        return (now - self.last_move_time) < self.cooldown_duration

    def remaining_cooldown(self, now: float | None = None) -> float:
        if self.last_move_time == 0.0:
            return 0.0
        if now is None:
            now = time.time()
        remaining = self.cooldown_duration - (now - self.last_move_time)
        return max(0.0, remaining)

    def to_dict(self, now: float | None = None) -> dict[str, Any]:
        d = {
            "type": self.piece_type.value,
            "color": self.color.value,
            "row": self.row,
            "col": self.col,
            "alive": self.alive,
            "cooldown_remaining": round(self.remaining_cooldown(now), 2),
            "piece_id": self.piece_id,
        }
        # Include relevant tags for client rendering
        if self.tags:
            visual_tags = {}
            for key in ("transformed", "is_wall", "is_duck", "booby_trapped",
                        "stun_until", "invulnerable_until", "marked_until", "is_clone"):
                if key in self.tags:
                    visual_tags[key] = self.tags[key]
            if visual_tags:
                d["tags"] = visual_tags
        return d


@dataclass
class Board:
    pieces: list[Piece] = field(default_factory=list)
    # En passant: set after a pawn double-advance (3-second window)
    en_passant_square: tuple[int, int] | None = None    # square where capturing pawn lands
    en_passant_pawn_pos: tuple[int, int] | None = None  # position of the capturable pawn
    en_passant_expires: float = 0.0
    _next_piece_id: int = 1

    def __post_init__(self):
        if not self.pieces:
            self._setup_initial_position()

    def _add_piece(self, piece_type: PieceType, color: Color, row: int, col: int) -> Piece:
        """Create a piece with auto-incremented ID and add it to the board."""
        p = Piece(piece_type=piece_type, color=color, row=row, col=col, piece_id=self._next_piece_id)
        self._next_piece_id += 1
        self.pieces.append(p)
        return p

    def _setup_initial_position(self):
        """Set up a standard chess starting position."""
        # White pieces (rows 0-1)
        back_row = [
            PieceType.ROOK, PieceType.KNIGHT, PieceType.BISHOP, PieceType.QUEEN,
            PieceType.KING, PieceType.BISHOP, PieceType.KNIGHT, PieceType.ROOK,
        ]

        for col, pt in enumerate(back_row):
            self._add_piece(pt, Color.WHITE, 0, col)

        for col in range(8):
            self._add_piece(PieceType.PAWN, Color.WHITE, 1, col)

        # Black pieces (rows 6-7)
        for col in range(8):
            self._add_piece(PieceType.PAWN, Color.BLACK, 6, col)

        for col, pt in enumerate(back_row):
            self._add_piece(pt, Color.BLACK, 7, col)

    def piece_at(self, row: int, col: int) -> Piece | None:
        """Return the alive piece at (row, col), or None."""
        for p in self.pieces:
            if p.alive and p.row == row and p.col == col:
                return p
        return None

    def king(self, color: Color) -> Piece | None:
        """Return the king of the given color."""
        for p in self.pieces:
            if p.alive and p.piece_type == PieceType.KING and p.color == color:
                return p
        return None

    def kings(self, color: Color) -> list[Piece]:
        """Return all alive kings of the given color (for multi-king mode)."""
        return [p for p in self.pieces if p.alive and p.piece_type == PieceType.KING and p.color == color]

    def to_state(self) -> list[dict[str, Any]]:
        """Serialize the board for sending to clients."""
        now = time.time()
        return [p.to_dict(now) for p in self.pieces if p.alive]
