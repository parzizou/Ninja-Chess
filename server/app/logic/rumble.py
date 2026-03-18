from __future__ import annotations

"""Rumble match state management.

A RumbleMatch tracks the full BO7 match between two players:
rounds won, augments chosen, current board, entities, timed effects, etc.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from app.logic.board import Board, Color, Piece, PieceType, COOLDOWNS
from app.logic.augments.base import BaseAugment, AugmentContext, BoardEntity
from app.logic.augments.registry import get_augment_by_id, get_random_augments
from app.logic.moves import is_valid_move


ROUNDS_TO_WIN = 3  # BO5


@dataclass
class RumbleMatch:
    match_id: str
    room_id: str
    white_sid: str
    black_sid: str
    white_user_id: int
    black_user_id: int
    white_username: str
    black_username: str

    # Match progress
    rounds_won: dict[str, int] = field(default_factory=lambda: {"white": 0, "black": 0})
    current_round: int = 1
    phase: str = "augment_select"  # augment_select, playing, round_over, match_over

    # Augments
    augments: dict[str, list[BaseAugment]] = field(default_factory=lambda: {"white": [], "black": []})
    used_augment_ids: dict[str, set[str]] = field(default_factory=lambda: {"white": set(), "black": set()})
    proposed: dict[str, list[BaseAugment]] = field(default_factory=lambda: {"white": [], "black": []})
    rerolls_used: dict[str, dict[int, bool]] = field(
        default_factory=lambda: {"white": {0: False, 1: False, 2: False},
                                  "black": {0: False, 1: False, 2: False}})
    selected: dict[str, str | None] = field(default_factory=lambda: {"white": None, "black": None})

    # Current round game state
    board: Board | None = None
    entities: list[BoardEntity] = field(default_factory=list)
    tags: dict[str, Any] = field(default_factory=dict)  # timed effects, flags

    # Activation cooldowns: (color, augment_id) -> last_activation_timestamp
    activation_cds: dict[tuple[str, str], float] = field(default_factory=dict)

    # Game state
    finished: bool = False
    round_finished: bool = False
    round_winner: str | None = None
    match_winner: str | None = None

    # Aura farming tracking
    aura_farming_winner: str | None = None  # color that won with aura_farming active

    def sid_color(self, sid: str) -> str | None:
        if sid == self.white_sid:
            return "white"
        if sid == self.black_sid:
            return "black"
        return None

    def opponent_sid(self, sid: str) -> str:
        return self.black_sid if sid == self.white_sid else self.white_sid

    def opponent_color(self, color: str) -> str:
        return "black" if color == "white" else "white"

    # ── Augment Selection ────────────────────────────────────────────────────

    def generate_proposals(self):
        """Generate 3 augment proposals for each player."""
        for color in ("white", "black"):
            # Check aura farming: opponent gets no augment this round
            opp = self.opponent_color(color)
            if self.aura_farming_winner == opp:
                self.proposed[color] = []
                self.selected[color] = "__skip__"
                continue

            owned_ids = self.used_augment_ids[color]
            # Build incompatibility set from owned augments
            incompat = set()
            for aug in self.augments[color]:
                incompat.add(aug.id)
                for inc in aug.incompatible_with:
                    incompat.add(inc)

            proposals = get_random_augments(3, exclude_ids=owned_ids, incompatible_ids=incompat)
            self.proposed[color] = proposals
            self.rerolls_used[color] = {i: False for i in range(len(proposals))}
            self.selected[color] = None

    def reroll_augment(self, color: str, index: int) -> BaseAugment | None:
        """Reroll a single proposed augment. Returns new augment or None if not allowed."""
        if index < 0 or index >= len(self.proposed[color]):
            return None

        # Check if aura_farming_winner gives infinite rerolls
        has_infinite = (self.aura_farming_winner == color)
        if not has_infinite and self.rerolls_used[color].get(index, True):
            return None

        self.rerolls_used[color][index] = True

        # Exclude already proposed + already owned
        exclude = self.used_augment_ids[color].copy()
        for i, aug in enumerate(self.proposed[color]):
            if i != index:
                exclude.add(aug.id)

        incompat = set()
        for aug in self.augments[color]:
            for inc in aug.incompatible_with:
                incompat.add(inc)

        replacements = get_random_augments(1, exclude_ids=exclude, incompatible_ids=incompat)
        if replacements:
            self.proposed[color][index] = replacements[0]
            if has_infinite:
                # Reset reroll for infinite mode
                self.rerolls_used[color][index] = False
            return replacements[0]
        return None

    def select_augment(self, color: str, augment_id: str) -> bool:
        """Player selects an augment from their proposals."""
        valid_ids = {a.id for a in self.proposed[color]}
        if augment_id not in valid_ids:
            return False
        aug = get_augment_by_id(augment_id)
        if not aug:
            return False
        self.selected[color] = augment_id
        return True

    def both_selected(self) -> bool:
        return all(self.selected[c] is not None for c in ("white", "black"))

    def apply_selections(self):
        """Finalize augment selection and prepare for the round."""
        for color in ("white", "black"):
            aug_id = self.selected[color]
            if aug_id and aug_id != "__skip__":
                aug = get_augment_by_id(aug_id)
                if aug:
                    self.augments[color].append(aug)
                    self.used_augment_ids[color].add(aug_id)
        # Reset aura farming state
        self.aura_farming_winner = None

    # ── Round Management ─────────────────────────────────────────────────────

    def start_round(self):
        """Initialize a new round with a fresh board."""
        self.board = Board()
        self.entities.clear()
        self.tags.clear()
        self.round_finished = False
        self.round_winner = None
        self.phase = "playing"

        now = time.time()
        effects = []
        for color in ("white", "black"):
            ctx = self._make_ctx(color, now)
            for aug in self.augments[color]:
                fx = aug.on_round_start(ctx)
                effects.extend(fx)

        return effects

    def end_round(self, winner_color: str):
        """Record round result."""
        self.round_finished = True
        self.round_winner = winner_color
        self.rounds_won[winner_color] += 1
        self.phase = "round_over"

        # Check aura_farming
        for aug in self.augments[winner_color]:
            if aug.id == "aura_farming":
                self.aura_farming_winner = winner_color

        if self.rounds_won[winner_color] >= ROUNDS_TO_WIN:
            self.finished = True
            self.match_winner = winner_color
            self.phase = "match_over"
            return True  # match over
        else:
            self.current_round += 1
            return False  # more rounds

    # ── Game Logic Helpers ───────────────────────────────────────────────────

    def _make_ctx(self, color: str, now: float | None = None) -> AugmentContext:
        return AugmentContext(
            board=self.board,
            player_color=color,
            opponent_color=self.opponent_color(color),
            match=self,
            now=now or time.time(),
        )

    def get_valid_moves(self, piece: Piece) -> set[tuple[int, int]]:
        """Compute all valid moves for a piece considering augments."""
        if not self.board:
            return set()

        color = piece.color.value
        now = time.time()

        # Check stun
        for c in ("white", "black"):
            ctx = self._make_ctx(c, now)
            for aug in self.augments[c]:
                if not aug.can_piece_move(piece, ctx):
                    return set()

        # Check wall
        if piece.tags.get("is_wall"):
            return set()

        # Standard moves
        moves = set()
        for r in range(8):
            for c in range(8):
                if is_valid_move(self.board, piece, r, c):
                    moves.add((r, c))

        # Apply augment modifications
        ctx = self._make_ctx(color, now)
        for aug in self.augments[color]:
            moves = aug.modify_moves(piece, moves, ctx)

        # Also check opponent augments that affect movement (e.g. stun from flashbang)
        opp = self.opponent_color(color)
        ctx_opp = self._make_ctx(opp, now)
        for aug in self.augments[opp]:
            moves = aug.modify_moves(piece, moves, ctx_opp)

        # Filter out squares blocked by entities (duck, wall)
        moves = self._filter_entity_blocked(piece, moves)

        return moves

    def _filter_entity_blocked(self, piece: Piece, moves: set[tuple[int, int]]) -> set[tuple[int, int]]:
        """Remove moves that require a sliding piece to pass through entity positions."""
        if piece.piece_type.value in ("knight", "pawn", "king"):
            # Non-sliding pieces: just remove entity squares themselves
            entity_positions = {(e.row, e.col) for e in self.entities if e.entity_type in ("duck", "wall")}
            return moves - entity_positions

        entity_positions = {(e.row, e.col) for e in self.entities if e.entity_type in ("duck", "wall")}
        if not entity_positions:
            return moves

        filtered = set()
        for (tr, tc) in moves:
            dr = tr - piece.row
            dc = tc - piece.col
            step_r = (1 if dr > 0 else -1) if dr != 0 else 0
            step_c = (1 if dc > 0 else -1) if dc != 0 else 0
            steps = max(abs(dr), abs(dc))
            blocked = False
            for i in range(1, steps + 1):  # includes target square
                r = piece.row + step_r * i
                c = piece.col + step_c * i
                if (r, c) in entity_positions:
                    blocked = True
                    break
            if not blocked:
                filtered.add((tr, tc))
        return filtered

    def compute_cooldown(self, piece: Piece) -> float:
        """Compute the effective cooldown for a piece after augment modifications."""
        base_cd = COOLDOWNS.get(piece.piece_type, 1.0)
        now = time.time()
        for color in ("white", "black"):
            ctx = self._make_ctx(color, now)
            for aug in self.augments[color]:
                base_cd = aug.modify_cooldown(piece, base_cd, ctx)
        return max(0.1, base_cd)

    def can_capture(self, piece: Piece, capturer: Piece) -> bool:
        """Check if a piece can be captured considering augments."""
        now = time.time()
        color = piece.color.value
        ctx = self._make_ctx(color, now)
        for aug in self.augments[color]:
            if not aug.can_be_captured(piece, capturer, ctx):
                return False
        return True

    def process_move_effects(self, piece: Piece, from_sq: tuple, to_sq: tuple,
                             captured: Piece | None) -> list[dict]:
        """Run augment hooks after a move. Returns effects to broadcast."""
        now = time.time()
        effects = []
        for color in ("white", "black"):
            ctx = self._make_ctx(color, now)
            for aug in self.augments[color]:
                fx = aug.on_move_done(piece, from_sq, to_sq, captured, ctx)
                effects.extend(fx)
        return effects

    def process_capture_effects(self, captured: Piece, capturer: Piece) -> list[dict]:
        """Run augment hooks after a capture. Returns effects."""
        now = time.time()
        effects = []
        for color in ("white", "black"):
            ctx = self._make_ctx(color, now)
            for aug in self.augments[color]:
                fx = aug.on_piece_captured(captured, capturer, ctx)
                effects.extend(fx)
        return effects

    def process_tick(self) -> list[dict]:
        """Run tick hooks for all augments. Returns effects."""
        now = time.time()
        effects = []
        for color in ("white", "black"):
            ctx = self._make_ctx(color, now)
            for aug in self.augments[color]:
                fx = aug.on_tick(ctx)
                effects.extend(fx)
        return effects

    def check_extra_wins(self) -> str | None:
        """Check if any augment triggers an alternative win condition."""
        now = time.time()
        for color in ("white", "black"):
            ctx = self._make_ctx(color, now)
            for aug in self.augments[color]:
                winner = aug.check_win(ctx)
                if winner:
                    return winner
        return None

    def check_king_capture(self, captured: Piece) -> bool:
        """Check if a king capture ends the round, considering multi-king mode."""
        if captured.piece_type != PieceType.KING:
            return False
        color = captured.color.value
        # Check for seconde_chance (king may have survived via hook)
        if captured.alive:
            return False
        # Multi-king: all kings must be dead
        multi = self.tags.get(f"multi_king_{color}", False)
        if multi:
            remaining = self.board.kings(Color(color))
            return len(remaining) == 0
        return True

    def can_activate(self, color: str, augment_id: str) -> tuple[bool, str]:
        """Check if a player can activate an augment."""
        now = time.time()

        # Silence check
        silence_until = self.tags.get(f"silence_{color}", 0)
        if now < silence_until:
            return False, "Silence actif"

        aug = None
        for a in self.augments[color]:
            if a.id == augment_id and a.is_activable:
                aug = a
                break
        if not aug:
            return False, "Augment non trouvé ou non activable"

        last_use = self.activation_cds.get((color, augment_id), 0)
        if now - last_use < aug.cooldown:
            remaining = aug.cooldown - (now - last_use)
            return False, f"Cooldown: {remaining:.1f}s"

        return True, ""

    def activate_augment(self, color: str, augment_id: str,
                         target_row: int | None = None,
                         target_col: int | None = None) -> dict:
        """Activate an augment and return effects."""
        now = time.time()
        aug = None
        for a in self.augments[color]:
            if a.id == augment_id and a.is_activable:
                aug = a
                break
        if not aug:
            return {"ok": False, "reason": "Augment introuvable"}

        ctx = self._make_ctx(color, now)
        result = aug.on_activate(ctx, target_row, target_col)

        if result.get("ok"):
            self.activation_cds[(color, augment_id)] = now

        return result

    def get_board_state(self, viewer_color: str) -> list[dict]:
        """Get board state for a specific viewer, applying visibility augments."""
        if not self.board:
            return []
        now = time.time()
        state = self.board.to_state()
        for color in ("white", "black"):
            ctx = self._make_ctx(color, now)
            for aug in self.augments[color]:
                state = aug.modify_visibility(state, viewer_color, ctx)
        return state

    def get_entities_for_viewer(self, viewer_color: str) -> list[dict]:
        """Get visible entities for a viewer (traps are hidden from opponent)."""
        result = []
        for e in self.entities:
            if e.entity_type == "trap" and e.owner_color != viewer_color:
                continue  # traps invisible to opponent
            result.append({
                "type": e.entity_type,
                "row": e.row, "col": e.col,
                "owner": e.owner_color,
            })
        return result
