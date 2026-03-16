from __future__ import annotations

import math
import random
import time

import arcade

from components.button import Button
from screens.game_screen import GameScreen, ClientPiece, CaptureEffect
from utils.constants import WINDOW_WIDTH, WINDOW_HEIGHT, COOLDOWNS

_PIECE_VALUES: dict[str, float] = {
    "pawn": 1.0, "knight": 3.0, "bishop": 3.0,
    "rook": 5.0, "queen": 9.0, "king": 1000.0,
}
_THINK_DELAYS: dict[str, tuple[float, float]] = {
    "easy": (1.2, 2.0), "medium": (0.5, 1.0), "hard": (0.1, 0.3),
}
_DIFF_LABELS = {"easy": "Facile", "medium": "Moyen", "hard": "Difficile"}
_EP_WINDOW = 3.0  # seconds en passant remains valid


class AIGameScreen(GameScreen):
    """Local Player vs AI — no server, no ELO impact."""

    def __init__(self, window: arcade.Window):
        super().__init__(window)
        self.ai_color = "black"
        self.difficulty = "medium"
        self.ai_think_timer = 0.0
        # Local en passant tracking
        self._ep_pawn_pos: tuple[int, int] | None = None
        self._ep_expires: float = 0.0

        self.replay_btn = Button(
            WINDOW_WIDTH / 2 - 90, WINDOW_HEIGHT / 2 - 80, 160, 46,
            "Rejouer", on_click=self._restart_game,
            color=(45, 120, 70), hover_color=(55, 145, 82), font_size=16,
        )
        self.menu_btn = Button(
            WINDOW_WIDTH / 2 + 90, WINDOW_HEIGHT / 2 - 80, 160, 46,
            "Menu", on_click=self._leave_game,
            color=(70, 70, 82), hover_color=(90, 90, 104), font_size=16,
        )

    # ── Setup ────────────────────────────────────────────────

    def _register_socket_events(self):
        pass

    def on_show(self):
        data = getattr(self.window, "game_init_data", None) or {}
        self.difficulty = data.get("difficulty", "medium")
        self._clear_selection()
        self._stop_drag()
        self.pending_move = None
        self.capture_effects.clear()
        self.game_over = False
        self.game_result = ""
        self.rematch_waiting = False
        self.en_passant_square = None
        self._ep_pawn_pos = None
        self._ep_expires = 0.0
        self.replay_btn.enabled = True
        self.replay_btn.text = "Rejouer"
        self.round_start_countdown = self.ROUND_START_COUNTDOWN
        self.round_start_fight_flash = self.ROUND_START_FIGHT_FLASH
        self.ai_think_timer = self.ROUND_START_COUNTDOWN + self.ROUND_START_FIGHT_FLASH + 0.5
        self.my_color = "white"
        self.ai_color = "black"
        self.opponent_name = f"IA ({_DIFF_LABELS.get(self.difficulty, self.difficulty)})"
        self._load_state(self._make_initial_state())
        self._load_sprites()

    @staticmethod
    def _make_initial_state() -> list[dict]:
        back = ["rook", "knight", "bishop", "queen", "king", "bishop", "knight", "rook"]
        state = []
        for col, ptype in enumerate(back):
            state.append({"type": ptype,  "color": "white", "row": 0, "col": col, "alive": True})
            state.append({"type": "pawn", "color": "white", "row": 1, "col": col, "alive": True})
            state.append({"type": "pawn", "color": "black", "row": 6, "col": col, "alive": True})
            state.append({"type": ptype,  "color": "black", "row": 7, "col": col, "alive": True})
        return state

    # ── Navigation ───────────────────────────────────────────

    def _leave_game(self):
        dest = "home" if getattr(self.window, "user_data", None) else "login"
        self.window.show_screen(dest)

    def _restart_game(self):
        self.window.game_init_data = {"difficulty": self.difficulty}
        self.on_show()

    def _request_rematch(self):
        self._restart_game()

    # ── Shared post-move logic ───────────────────────────────

    def _apply_move(
        self,
        piece: ClientPiece,
        from_row: int, from_col: int,
        to_row: int, to_col: int,
        mover_color: str,
    ) -> bool:
        """Execute a move locally. Returns True if king was captured (game over)."""
        now = time.time()

        # ── Castling ─────────────────────────────────────────
        if piece.piece_type == "king" and abs(to_col - from_col) == 2:
            rook_from = 7 if to_col > from_col else 0
            rook_to   = 5 if to_col > from_col else 3
            rook = self._piece_at(from_row, rook_from)
            if rook:
                old_x, old_y = self._board_to_screen(rook.row, rook.col)
                rook.anim_from_x = old_x
                rook.anim_from_y = old_y
                rook.anim_progress = 0.0
                rook.col = rook_to
                rook.last_move_time = now

        # ── En passant capture ────────────────────────────────
        is_ep = (
            piece.piece_type == "pawn"
            and from_col != to_col
            and self._piece_at(to_row, to_col) is None
            and self.en_passant_square == (to_row, to_col)
            and self._ep_expires > now
        )
        if is_ep and self._ep_pawn_pos:
            ep_pawn = self._piece_at(*self._ep_pawn_pos)
            if ep_pawn:
                ep_pawn.alive = False
                sx, sy = self._board_to_screen(ep_pawn.row, ep_pawn.col)
                self.capture_effects.append(CaptureEffect(x=sx, y=sy))

        # ── Normal capture ────────────────────────────────────
        captured = self._piece_at(to_row, to_col) if not is_ep else None
        if captured and captured.alive:
            captured.alive = False
            sx, sy = self._board_to_screen(captured.row, captured.col)
            self.capture_effects.append(CaptureEffect(x=sx, y=sy))
            if captured.piece_type == "king":
                piece.row = to_row
                piece.col = to_col
                piece.cooldown_total = COOLDOWNS.get(piece.piece_type, 1.0)
                piece.last_move_time = now
                return True  # game over

        # ── Apply move ────────────────────────────────────────
        piece.row = to_row
        piece.col = to_col
        piece.cooldown_total = COOLDOWNS.get(piece.piece_type, 1.0)
        piece.last_move_time = now

        # ── Update EP state ───────────────────────────────────
        if piece.piece_type == "pawn" and abs(to_row - from_row) == 2:
            ep_row = (from_row + to_row) // 2
            self.en_passant_square = (ep_row, to_col)
            self._ep_pawn_pos = (to_row, to_col)
            self._ep_expires = now + _EP_WINDOW
        else:
            self.en_passant_square = None
            self._ep_pawn_pos = None
            self._ep_expires = 0.0

        # ── Promotion ─────────────────────────────────────────
        promo_row = 7 if mover_color == "white" else 0
        if piece.piece_type == "pawn" and piece.row == promo_row:
            piece.piece_type = "queen"
            piece.cooldown_total = COOLDOWNS.get("queen", 5.0)

        # ── Check: reset opponent king cooldown ───────────────
        opp_color = "black" if mover_color == "white" else "white"
        opp_king_in_check = self._is_in_check_local(opp_color)
        if opp_king_in_check:
            for p in self.pieces:
                if p.alive and p.piece_type == "king" and p.color == opp_color:
                    p.last_move_time = 0.0
                    break

        return False

    def _is_in_check_local(self, color: str) -> bool:
        """Check if the king of *color* is attacked by any opponent piece."""
        king = next((p for p in self.pieces if p.alive and p.piece_type == "king" and p.color == color), None)
        if not king:
            return False
        opp = "black" if color == "white" else "white"
        for p in self.pieces:
            if p.alive and p.color == opp and self._can_attack_local(p, king.row, king.col):
                return True
        return False

    def _can_attack_local(self, attacker: ClientPiece, to_r: int, to_c: int) -> bool:
        """Can *attacker* reach (to_r, to_c)? (no castling, no EP)"""
        dr = to_r - attacker.row
        dc = to_c - attacker.col
        match attacker.piece_type:
            case "pawn":
                direction = 1 if attacker.color == "white" else -1
                return abs(dc) == 1 and dr == direction
            case "knight":
                return (abs(dr), abs(dc)) in ((2, 1), (1, 2))
            case "bishop":
                if abs(dr) == abs(dc) and dr != 0:
                    return self._path_clear(attacker, dr, dc)
            case "rook":
                if (dr == 0) != (dc == 0):
                    return self._path_clear(attacker, dr, dc)
            case "queen":
                if (abs(dr) == abs(dc) and dr != 0) or ((dr == 0) != (dc == 0)):
                    return self._path_clear(attacker, dr, dc)
            case "king":
                return abs(dr) <= 1 and abs(dc) <= 1
        return False

    # ── Player move ──────────────────────────────────────────

    def _try_move(self, piece: ClientPiece, to_row: int, to_col: int):
        if self._is_round_start_locked():
            return
        if piece.is_on_cooldown():
            return
        if (to_row, to_col) not in self.valid_highlights:
            return

        old_x, old_y = self._board_to_screen(piece.row, piece.col)
        piece.anim_from_x = old_x
        piece.anim_from_y = old_y
        piece.anim_progress = 0.0

        from_row, from_col = piece.row, piece.col
        game_over = self._apply_move(piece, from_row, from_col, to_row, to_col, self.my_color)

        self._stop_drag()
        self._clear_selection()

        if game_over:
            self.game_over = True
            self.game_result = "Victoire !"
            return

        lo, hi = _THINK_DELAYS.get(self.difficulty, (0.5, 1.0))
        self.ai_think_timer = lo + random.random() * (hi - lo)

    # ── AI update loop ───────────────────────────────────────

    def on_update(self, dt: float):
        super().on_update(dt)
        if not self.game_over and not self._is_round_start_locked():
            self._ai_update(dt)

    def _ai_update(self, dt: float):
        if self.ai_think_timer > 0:
            self.ai_think_timer -= dt
            return

        available = [
            p for p in self.pieces
            if p.alive and p.color == self.ai_color and not p.is_on_cooldown()
        ]
        if not available:
            return

        move = self._ai_pick_move(available)
        if move:
            piece, to_r, to_c = move
            old_x, old_y = self._board_to_screen(piece.row, piece.col)
            piece.anim_from_x = old_x
            piece.anim_from_y = old_y
            piece.anim_progress = 0.0

            from_r, from_c = piece.row, piece.col
            game_over = self._apply_move(piece, from_r, from_c, to_r, to_c, self.ai_color)
            if game_over:
                self.game_over = True
                self.game_result = "Défaite..."
                return

            lo, hi = _THINK_DELAYS.get(self.difficulty, (0.5, 1.0))
            self.ai_think_timer = lo + random.random() * (hi - lo)

    # ── AI move selection ────────────────────────────────────

    def _ai_pick_move(self, available: list[ClientPiece]) -> tuple[ClientPiece, int, int] | None:
        all_moves: list[tuple[ClientPiece, int, int]] = []
        for piece in available:
            for r, c in self._get_basic_moves(piece):
                all_moves.append((piece, r, c))
        if not all_moves:
            return None
        match self.difficulty:
            case "easy":
                return random.choice(all_moves)
            case "medium":
                return self._pick_medium(all_moves)
            case _:
                return self._pick_hard(all_moves)

    def _pick_medium(self, moves: list[tuple]) -> tuple:
        captures: list[tuple[float, ClientPiece, int, int]] = []
        for piece, r, c in moves:
            target = self._piece_at(r, c)
            if target and target.alive and target.color != self.ai_color:
                captures.append((_PIECE_VALUES.get(target.piece_type, 0.0), piece, r, c))
        if captures:
            captures.sort(reverse=True)
            top_val = captures[0][0]
            best = [(p, r, c) for v, p, r, c in captures if v == top_val]
            return random.choice(best)
        return random.choice(moves)

    def _pick_hard(self, moves: list[tuple]) -> tuple:
        best_score = -math.inf
        best: list[tuple] = []
        for piece, to_r, to_c in moves:
            score = self._score_move(piece, to_r, to_c)
            if score == math.inf:
                return piece, to_r, to_c
            if score > best_score:
                best_score = score
                best = [(piece, to_r, to_c)]
            elif score == best_score:
                best.append((piece, to_r, to_c))
        return random.choice(best) if best else random.choice(moves)

    def _score_move(self, piece: ClientPiece, to_r: int, to_c: int) -> float:
        captured = self._piece_at(to_r, to_c)
        gain = 0.0
        if captured and captured.alive:
            if captured.piece_type == "king":
                return math.inf
            gain = _PIECE_VALUES.get(captured.piece_type, 0.0)

        old_r, old_c = piece.row, piece.col
        piece.row, piece.col = to_r, to_c
        if captured:
            captured.alive = False

        risk = 0.0
        for opp in self.pieces:
            if not opp.alive or opp.color == self.ai_color:
                continue
            if (to_r, to_c) in self._get_basic_moves(opp):
                risk = _PIECE_VALUES.get(piece.piece_type, 0.0)
                break

        piece.row, piece.col = old_r, old_c
        if captured:
            captured.alive = True
        return gain - risk

    # ── Game-over overlay ────────────────────────────────────

    def _draw_game_over(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, (0, 0, 0, 160),
        )
        color = (100, 255, 100) if "Victoire" in self.game_result else (255, 100, 100)
        arcade.draw_text(
            self.game_result,
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 60,
            color, font_size=36, anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            "Rejouer ou retourner au menu",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 12,
            (180, 180, 180), font_size=14, anchor_x="center", anchor_y="center",
        )
        self.replay_btn.draw()
        self.menu_btn.draw()
