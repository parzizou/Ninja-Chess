from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.logic.board import Board, Piece, Color


@dataclass
class BoardEntity:
    """A special entity placed on the board by an augment (duck, trap, wall, meteor)."""
    entity_type: str  # "duck", "trap", "meteor", "wall"
    row: int
    col: int
    owner_color: str  # "white" or "black"
    created_at: float = 0.0
    expires_at: float = 0.0  # 0 = permanent until removed
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AugmentContext:
    """Context passed to augment hooks, giving access to match state."""
    board: Any  # Board
    player_color: str  # color of the augment owner
    opponent_color: str
    match: Any  # RumbleMatch
    now: float = 0.0

    @property
    def entities(self) -> list[BoardEntity]:
        return self.match.entities

    def count_alive(self, color: str) -> int:
        return sum(1 for p in self.board.pieces if p.alive and p.color.value == color)

    def get_pieces(self, color: str) -> list:
        return [p for p in self.board.pieces if p.alive and p.color.value == color]

    def piece_at(self, row: int, col: int):
        return self.board.piece_at(row, col)

    def entity_at(self, row: int, col: int) -> BoardEntity | None:
        for e in self.entities:
            if e.row == row and e.col == col:
                return e
        return None

    def remove_entity(self, entity: BoardEntity):
        if entity in self.entities:
            self.entities.remove(entity)

    def add_entity(self, entity: BoardEntity):
        self.entities.append(entity)


class BaseAugment:
    """Base class for all augments. Override hooks as needed."""

    id: str = ""
    name: str = ""
    description: str = ""
    is_activable: bool = False
    cooldown: float = 0.0  # activation cooldown in seconds
    target_type: str = "none"  # "none", "square", "ally_piece", "enemy_piece", "own_pawn"
    incompatible_with: list[str] = []

    def on_round_start(self, ctx: AugmentContext) -> list[dict]:
        """Called when a new round starts. Return list of effect dicts to send to clients."""
        return []

    def modify_moves(self, piece: Any, moves: set[tuple[int, int]], ctx: AugmentContext) -> set[tuple[int, int]]:
        """Add or remove valid target squares for a piece."""
        return moves

    def modify_cooldown(self, piece: Any, base_cd: float, ctx: AugmentContext) -> float:
        """Modify the cooldown duration for a piece. Return adjusted CD."""
        return base_cd

    def on_move_done(self, piece: Any, from_sq: tuple[int, int], to_sq: tuple[int, int],
                     captured: Any | None, ctx: AugmentContext) -> list[dict]:
        """Called after a move is executed. Return list of effect dicts."""
        return []

    def on_piece_captured(self, captured: Any, capturer: Any, ctx: AugmentContext) -> list[dict]:
        """Called when a piece is captured. Return list of effect dicts."""
        return []

    def on_activate(self, ctx: AugmentContext, target_row: int | None = None,
                    target_col: int | None = None) -> dict:
        """Called when the augment is manually activated. Return effect dict."""
        return {}

    def on_tick(self, ctx: AugmentContext) -> list[dict]:
        """Called periodically to process timed effects. Return list of effect dicts."""
        return []

    def check_win(self, ctx: AugmentContext) -> str | None:
        """Check for alternative win condition. Return winner color string or None."""
        return None

    def can_piece_move(self, piece: Any, ctx: AugmentContext) -> bool:
        """Return False to prevent a piece from moving (e.g. stun)."""
        return True

    def can_be_captured(self, piece: Any, capturer: Any, ctx: AugmentContext) -> bool:
        """Return False to prevent a piece from being captured (e.g. invulnerability)."""
        return True

    def modify_visibility(self, state: list[dict], viewer_color: str, ctx: AugmentContext) -> list[dict]:
        """Modify the board state sent to a specific player (e.g. fog of war)."""
        return state

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_activable": self.is_activable,
            "cooldown": self.cooldown,
            "target_type": self.target_type,
        }
