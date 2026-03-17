from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass

import arcade

from components.button import Button
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT,
    BOARD_SIZE, SQUARE_SIZE, BOARD_PIXEL, BOARD_OFFSET_X, BOARD_OFFSET_Y,
    COLOR_LIGHT_SQUARE, COLOR_DARK_SQUARE, COLOR_HIGHLIGHT,
    COOLDOWNS, SPRITES_DIR,
)
from utils.socket_client import socket_client


# ── Data classes ────────────────────────────────────────────

@dataclass
class ClientPiece:
    piece_type: str
    color: str  # "white" or "black"
    row: int
    col: int
    alive: bool = True
    cooldown_remaining: float = 0.0
    cooldown_total: float = 0.0
    last_move_time: float = 0.0

    # Animation
    anim_from_x: float | None = None
    anim_from_y: float | None = None
    anim_progress: float = 1.0  # 1.0 = no animation

    @property
    def sprite_name(self) -> str:
        return f"{self.color}_{self.piece_type}"

    def is_on_cooldown(self) -> bool:
        if self.last_move_time == 0.0:
            return False
        elapsed = time.time() - self.last_move_time
        return elapsed < self.cooldown_total

    def remaining_cd(self) -> float:
        if self.last_move_time == 0.0:
            return 0.0
        elapsed = time.time() - self.last_move_time
        return max(0.0, self.cooldown_total - elapsed)

    def cd_fraction(self) -> float:
        """Return 0.0 (ready) to 1.0 (just moved) fraction of cooldown remaining."""
        if self.cooldown_total <= 0:
            return 0.0
        rem = self.remaining_cd()
        return rem / self.cooldown_total


@dataclass
class CaptureEffect:
    x: float
    y: float
    timer: float = 0.0
    duration: float = 0.4


@dataclass
class PendingMove:
    piece: ClientPiece
    from_row: int
    from_col: int
    to_row: int
    to_col: int


class GameScreen:
    """The main chess game screen with real-time gameplay."""

    ANIM_SPEED = 8.0  # animation interpolation speed
    ROUND_START_COUNTDOWN = 3.0
    ROUND_START_FIGHT_FLASH = 0.55

    def __init__(self, window: arcade.Window):
        self.window = window
        self.my_color: str = "white"
        self.opponent_name: str = ""
        self.pieces: list[ClientPiece] = []
        self.selected_piece: ClientPiece | None = None
        self.valid_highlights: list[tuple[int, int]] = []
        self.dragging_piece: ClientPiece | None = None
        self.drag_x: float = 0.0
        self.drag_y: float = 0.0
        self.drag_hover_square: tuple[int, int] | None = None
        self.pending_move: PendingMove | None = None
        self.capture_effects: list[CaptureEffect] = []
        self.game_over = False
        self.game_result: str = ""
        self.rematch_waiting = False
        self.en_passant_square: tuple[int, int] | None = None  # (row, col) EP target square

        self.round_start_countdown = self.ROUND_START_COUNTDOWN
        self.round_start_fight_flash = self.ROUND_START_FIGHT_FLASH

        self.sprite_cache: dict[str, arcade.Texture] = {}
        self._sprite_list = arcade.SpriteList()

        self.back_btn = Button(
            80, WINDOW_HEIGHT - 25, 100, 30,
            "← Quitter", on_click=self._leave_game,
            color=(80, 40, 40), font_size=12,
        )
        self.replay_btn = Button(
            WINDOW_WIDTH / 2 - 90, WINDOW_HEIGHT / 2 - 80, 160, 46,
            "Rejouer", on_click=self._request_rematch,
            color=(45, 120, 70), hover_color=(55, 145, 82), font_size=16,
        )
        self.menu_btn = Button(
            WINDOW_WIDTH / 2 + 90, WINDOW_HEIGHT / 2 - 80, 160, 46,
            "Menu", on_click=self._leave_game,
            color=(70, 70, 82), hover_color=(90, 90, 104), font_size=16,
        )

        self._register_socket_events()

    def _register_socket_events(self):
        socket_client.on("game:move_ack", self._on_move_ack)
        socket_client.on("game:opponent_move", self._on_opponent_move)
        socket_client.on("game:over", self._on_game_over)
        socket_client.on("game:rematch_waiting", self._on_rematch_waiting)
        socket_client.on("game:rematch_unavailable", self._on_rematch_unavailable)

    def on_show(self):
        """Initialize from game_init_data set by room_screen."""
        data = getattr(self.window, "game_init_data", None)
        if not data:
            return
        self._clear_selection()
        self._stop_drag()
        self.pending_move = None
        self.capture_effects.clear()
        self.game_over = False
        self.game_result = ""
        self.rematch_waiting = False
        self.en_passant_square = None
        self.replay_btn.enabled = True
        self.replay_btn.text = "Rejouer"
        self.round_start_countdown = self.ROUND_START_COUNTDOWN
        self.round_start_fight_flash = self.ROUND_START_FIGHT_FLASH
        self.my_color = data.get("your_color", "white")
        self.opponent_name = data.get("black") if self.my_color == "white" else data.get("white")
        state = data.get("state", [])
        self._load_state(state)
        self._load_sprites()

    def _is_round_start_locked(self) -> bool:
        return self.round_start_countdown > 0.0 or self.round_start_fight_flash > 0.0

    def _load_state(self, state: list[dict]):
        self.pieces.clear()
        for p in state:
            self.pieces.append(ClientPiece(
                piece_type=p["type"],
                color=p["color"],
                row=p["row"],
                col=p["col"],
                alive=p.get("alive", True),
                cooldown_remaining=p.get("cooldown_remaining", 0.0),
                cooldown_total=COOLDOWNS.get(p["type"], 1.0),
            ))

    def _load_sprites(self):
        """Load piece sprite textures from disk."""
        for name in [
            "white_king", "white_queen", "white_bishop", "white_knight", "white_rook", "white_pawn",
            "black_king", "black_queen", "black_bishop", "black_knight", "black_rook", "black_pawn",
        ]:
            path = os.path.join(SPRITES_DIR, f"{name}.png")
            if os.path.exists(path):
                self.sprite_cache[name] = arcade.load_texture(path)

    def _board_to_screen(self, row: int, col: int) -> tuple[float, float]:
        """Convert board (row, col) to screen pixel coordinates.

        If playing as black, the board is flipped so our pieces are at the bottom.
        """
        if self.my_color == "black":
            display_row = 7 - row
            display_col = 7 - col
        else:
            display_row = row
            display_col = col

        x = BOARD_OFFSET_X + display_col * SQUARE_SIZE + SQUARE_SIZE / 2
        y = BOARD_OFFSET_Y + display_row * SQUARE_SIZE + SQUARE_SIZE / 2
        return x, y

    def _screen_to_board(self, sx: float, sy: float) -> tuple[int, int] | None:
        """Convert screen pixel to board (row, col), or None if off-board."""
        col = int((sx - BOARD_OFFSET_X) / SQUARE_SIZE)
        row = int((sy - BOARD_OFFSET_Y) / SQUARE_SIZE)

        if self.my_color == "black":
            row = 7 - row
            col = 7 - col

        if 0 <= row < 8 and 0 <= col < 8:
            return row, col
        return None

    def _piece_at(self, row: int, col: int) -> ClientPiece | None:
        for p in self.pieces:
            if p.alive and p.row == row and p.col == col:
                return p
        return None

    # ── Socket handlers ─────────────────────────────────────

    def _on_move_ack(self, data):
        if not data.get("ok"):
            if self.pending_move:
                piece = self.pending_move.piece
                if piece.alive:
                    piece.row = self.pending_move.from_row
                    piece.col = self.pending_move.from_col
                    piece.anim_from_x = None
                    piece.anim_from_y = None
                    piece.anim_progress = 1.0
                self.pending_move = None
            return

        to_r, to_c = data["to_row"], data["to_col"]
        piece = self._piece_at(to_r, to_c)
        if piece:
            piece.cooldown_total = data.get("cooldown", COOLDOWNS.get(piece.piece_type, 1.0))
            piece.last_move_time = time.time()
            if data.get("promoted"):
                piece.piece_type = "queen"
                piece.cooldown_total = COOLDOWNS.get("queen", 5.0)

        self.pending_move = None

        if data.get("captured"):
            self._apply_capture(data["captured"])

        # Castling: animate rook
        cr = data.get("castling_rook")
        if cr:
            self._apply_castling_rook(cr)

        # EP square for future highlighting
        ep = data.get("en_passant_square")
        self.en_passant_square = tuple(ep) if ep else None

        # Opponent king in check → their CD resets (visual only, server already reset it)
        if data.get("opponent_king_in_check"):
            opp_color = "black" if self.my_color == "white" else "white"
            for p in self.pieces:
                if p.alive and p.piece_type == "king" and p.color == opp_color:
                    p.last_move_time = 0.0
                    break

    def _on_opponent_move(self, data):
        from_r, from_c = data["from_row"], data["from_col"]
        to_r, to_c = data["to_row"], data["to_col"]

        piece = self._piece_at(from_r, from_c)
        if piece:
            old_x, old_y = self._board_to_screen(piece.row, piece.col)
            piece.anim_from_x = old_x
            piece.anim_from_y = old_y
            piece.anim_progress = 0.0
            piece.row = to_r
            piece.col = to_c
            piece.cooldown_total = data.get("cooldown", COOLDOWNS.get(piece.piece_type, 1.0))
            piece.last_move_time = time.time()
            if data.get("promoted"):
                piece.piece_type = "queen"
                piece.cooldown_total = COOLDOWNS.get("queen", 5.0)

        if data.get("captured"):
            self._apply_capture(data["captured"])

        cr = data.get("castling_rook")
        if cr:
            self._apply_castling_rook(cr)

        ep = data.get("en_passant_square")
        self.en_passant_square = tuple(ep) if ep else None

        # My king is in check → reset its cooldown
        if data.get("my_king_in_check"):
            for p in self.pieces:
                if p.alive and p.piece_type == "king" and p.color == self.my_color:
                    p.last_move_time = 0.0
                    break

    def _apply_castling_rook(self, cr: dict):
        """Animate the rook as part of a castling move."""
        rook = self._piece_at(cr["row"], cr["from_col"])
        if rook:
            old_x, old_y = self._board_to_screen(rook.row, rook.col)
            rook.anim_from_x = old_x
            rook.anim_from_y = old_y
            rook.anim_progress = 0.0
            rook.col = cr["to_col"]

    def _apply_capture(self, cap_data: dict):
        """Remove captured piece and add visual effect."""
        for p in self.pieces:
            if (p.alive and p.row == cap_data["row"] and p.col == cap_data["col"]
                    and p.color == cap_data["color"] and p.piece_type == cap_data["type"]):
                p.alive = False
                sx, sy = self._board_to_screen(p.row, p.col)
                self.capture_effects.append(CaptureEffect(x=sx, y=sy))
                break

    def _on_game_over(self, data):
        self.game_over = True
        winner = data.get("winner", "")
        reason = data.get("reason", "")
        if winner == self.my_color:
            self.game_result = "Victoire !"
        else:
            self.game_result = "Défaite..."
        if reason == "opponent_disconnected":
            self.game_result += " (adversaire déconnecté)"
        self.rematch_waiting = False
        self.replay_btn.enabled = True
        self.replay_btn.text = "Rejouer"

    def _on_rematch_waiting(self, data):
        self.rematch_waiting = True
        self.replay_btn.enabled = False
        self.replay_btn.text = "En attente..."

    def _on_rematch_unavailable(self, data):
        self.rematch_waiting = False
        self.replay_btn.enabled = True
        self.replay_btn.text = "Rejouer"

    def _leave_game(self):
        socket_client.emit("room:leave")
        self.window.show_screen("home")

    # ── Drawing ─────────────────────────────────────────────

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )
        self._draw_board()
        self._draw_highlights()
        self._draw_pieces()
        self._draw_check_indicators()
        self._draw_capture_effects()
        self._draw_ui()

        if self._is_round_start_locked() and not self.game_over:
            self._draw_round_start_countdown()

        if self.game_over:
            self._draw_game_over()

    def _draw_board(self):
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                x, y = self._board_to_screen(row, col)
                is_light = (row + col) % 2 == 0
                color = COLOR_DARK_SQUARE if is_light else COLOR_LIGHT_SQUARE
                arcade.draw_rectangle_filled(x, y, SQUARE_SIZE, SQUARE_SIZE, color)

        # Board border
        bx = BOARD_OFFSET_X + BOARD_PIXEL / 2
        by = BOARD_OFFSET_Y + BOARD_PIXEL / 2
        arcade.draw_rectangle_outline(bx, by, BOARD_PIXEL, BOARD_PIXEL, (100, 80, 60), 3)

    def _draw_highlights(self):
        """Draw valid move highlights for the selected piece."""
        pulse = 0.5 + 0.5 * math.sin(time.time() * 7.0)
        for row, col in self.valid_highlights:
            x, y = self._board_to_screen(row, col)
            arcade.draw_rectangle_filled(x, y, SQUARE_SIZE, SQUARE_SIZE, COLOR_HIGHLIGHT)

            # Add a small glowing point at center to make legal targets pop.
            outer_r = SQUARE_SIZE * (0.16 + 0.03 * pulse)
            inner_r = SQUARE_SIZE * (0.06 + 0.012 * pulse)
            arcade.draw_circle_filled(x, y, outer_r, (255, 245, 180, 45))
            arcade.draw_circle_filled(x, y, inner_r, (255, 250, 200, 180))

        if self.drag_hover_square and self.drag_hover_square in self.valid_highlights:
            row, col = self.drag_hover_square
            x, y = self._board_to_screen(row, col)
            arcade.draw_rectangle_outline(
                x, y,
                SQUARE_SIZE * 0.88,
                SQUARE_SIZE * 0.88,
                (255, 245, 190, 220),
                3,
            )

        # Selected square
        if self.selected_piece:
            x, y = self._board_to_screen(self.selected_piece.row, self.selected_piece.col)
            arcade.draw_rectangle_filled(x, y, SQUARE_SIZE, SQUARE_SIZE, (100, 200, 100, 80))

    def _draw_pieces(self):
        dragged_piece = self.dragging_piece if self.dragging_piece and self.dragging_piece.alive else None

        for piece in self.pieces:
            if not piece.alive:
                continue
            if dragged_piece is piece:
                continue

            target_x, target_y = self._board_to_screen(piece.row, piece.col)

            # Interpolate animation
            if piece.anim_progress < 1.0:
                ax = piece.anim_from_x or target_x
                ay = piece.anim_from_y or target_y
                t = piece.anim_progress
                draw_x = ax + (target_x - ax) * t
                draw_y = ay + (target_y - ay) * t
            else:
                draw_x = target_x
                draw_y = target_y

            # Alpha: dimmed if on cooldown (own pieces only)
            is_mine = piece.color == self.my_color
            on_cd = piece.is_on_cooldown()
            alpha = 140 if (is_mine and on_cd) else 255

            self._draw_piece_visual(piece, draw_x, draw_y, alpha)

            # Cooldown ring
            if on_cd:
                self._draw_cooldown_indicator(piece, draw_x, draw_y, is_mine)

        if dragged_piece:
            self._draw_piece_visual(dragged_piece, self.drag_x, self.drag_y, 245, size_mult=1.08)

    def _draw_piece_visual(
            self,
            piece: ClientPiece,
            x: float,
            y: float,
            alpha: int,
            size_mult: float = 1.0):
        tex = self.sprite_cache.get(piece.sprite_name)
        if tex:
            self._sprite_list.clear(deep=False)
            sp = arcade.Sprite(tex)
            sp.center_x = x
            sp.center_y = y
            sp.width = SQUARE_SIZE * 0.85 * size_mult
            sp.height = SQUARE_SIZE * 0.85 * size_mult
            sp.alpha = alpha
            self._sprite_list.append(sp)
            self._sprite_list.draw()
        else:
            self._draw_piece_fallback(piece, x, y, alpha, size_mult=size_mult)

    def _draw_piece_fallback(
            self,
            piece: ClientPiece,
            x: float,
            y: float,
            alpha: int,
            size_mult: float = 1.0):
        """Draw a text-based piece when sprites aren't available."""
        symbols = {
            ("white", "king"): "♔", ("white", "queen"): "♕",
            ("white", "rook"): "♖", ("white", "bishop"): "♗",
            ("white", "knight"): "♘", ("white", "pawn"): "♙",
            ("black", "king"): "♚", ("black", "queen"): "♛",
            ("black", "rook"): "♜", ("black", "bishop"): "♝",
            ("black", "knight"): "♞", ("black", "pawn"): "♟",
        }
        sym = symbols.get((piece.color, piece.piece_type), "?")

        # Draw a colored circle background
        if piece.color == "white":
            bg = (240, 240, 240, alpha)
            fg = (30, 30, 30, alpha)
        else:
            bg = (50, 50, 50, alpha)
            fg = (230, 230, 230, alpha)

        radius = SQUARE_SIZE * 0.35 * size_mult
        arcade.draw_circle_filled(x, y, radius, bg)
        arcade.draw_circle_outline(x, y, radius, (0, 0, 0, 100), 2)
        arcade.draw_text(
            sym, x, y, fg, font_size=int(28 * size_mult),
            anchor_x="center", anchor_y="center",
        )

    def _draw_cooldown_indicator(self, piece: ClientPiece, x: float, y: float, is_mine: bool):
        """Draw cooldown visualization."""
        frac = piece.cd_fraction()
        if frac <= 0:
            return

        if is_mine:
            # Cooldown pie overlay
            radius = SQUARE_SIZE * 0.4
            segments = 32
            angle_end = 360 * frac

            # Filled pie slice
            points = [(x, y)]
            for i in range(segments + 1):
                a = 90 - (angle_end * i / segments)
                rad = math.radians(a)
                px = x + radius * math.cos(rad)
                py = y + radius * math.sin(rad)
                points.append((px, py))

            if len(points) >= 3:
                arcade.draw_polygon_filled(points, (200, 60, 60, 80))

            # Arc outline (manual line segments)
            arc_points = []
            for i in range(segments + 1):
                a = 90 - (angle_end * i / segments)
                rad = math.radians(a)
                arc_points.append((x + radius * math.cos(rad), y + radius * math.sin(rad)))
            for i in range(len(arc_points) - 1):
                arcade.draw_line(
                    arc_points[i][0], arc_points[i][1],
                    arc_points[i + 1][0], arc_points[i + 1][1],
                    (200, 60, 60, 180), 3,
                )
        else:
            # Small red bubble above enemy piece
            remaining = piece.remaining_cd()
            if remaining > 0:
                bx = x + SQUARE_SIZE * 0.3
                by = y + SQUARE_SIZE * 0.35
                arcade.draw_circle_filled(bx, by, 12, (200, 50, 50, 200))
                arcade.draw_text(
                    f"{remaining:.1f}",
                    bx, by, (255, 255, 255), font_size=8,
                    anchor_x="center", anchor_y="center", bold=True,
                )

    def _draw_capture_effects(self):
        for eff in self.capture_effects:
            t = eff.timer / eff.duration
            alpha = int(255 * (1.0 - t))
            radius = 20 + 30 * t
            arcade.draw_circle_filled(eff.x, eff.y, radius, (255, 100, 50, alpha))
            arcade.draw_circle_outline(eff.x, eff.y, radius, (255, 200, 100, alpha), 2)

    def _draw_check_indicators(self):
        """Draw red glow on kings in check and threat arrows from attackers."""
        pulse = 0.5 + 0.5 * math.sin(time.time() * 6.0)
        for color in ("white", "black"):
            attackers = self._find_attackers(color)
            if not attackers:
                continue
            king = next((p for p in self.pieces if p.alive and p.piece_type == "king" and p.color == color), None)
            if not king:
                continue
            kx, ky = self._board_to_screen(king.row, king.col)
            # Pulsing red square overlay on king
            arcade.draw_rectangle_filled(kx, ky, SQUARE_SIZE, SQUARE_SIZE, (220, 20, 20, int(90 + 60 * pulse)))
            # Pulsing ring around king
            arcade.draw_circle_outline(kx, ky, SQUARE_SIZE * (0.42 + 0.08 * pulse), (255, 60, 60, 200), 3)
            # Threat arrow from each attacker (max 2 to avoid clutter)
            for attacker in attackers[:2]:
                ax, ay = self._board_to_screen(attacker.row, attacker.col)
                self._draw_threat_arrow(ax, ay, kx, ky)

    def _draw_threat_arrow(self, x1: float, y1: float, x2: float, y2: float):
        """Draw an arrow from (x1,y1) toward (x2,y2), padded so it clears piece sprites."""
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1:
            return
        nx, ny = dx / length, dy / length
        pad = SQUARE_SIZE * 0.4
        sx, sy = x1 + nx * pad, y1 + ny * pad
        ex, ey = x2 - nx * pad, y2 - ny * pad
        color = (255, 80, 80, 200)
        arcade.draw_line(sx, sy, ex, ey, color, 3)
        head_len = 12
        for side in (0.45, -0.45):
            angle = math.atan2(ny, nx) + math.pi + side
            arcade.draw_line(ex, ey, ex + head_len * math.cos(angle), ey + head_len * math.sin(angle), color, 3)

    def _draw_ui(self):
        self.back_btn.draw()

        user = getattr(self.window, "user_data", None)
        my_name = user["username"] if user else "Vous"

        # Top: opponent info
        arcade.draw_text(
            f"Adversaire : {self.opponent_name}",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 20,
            (200, 200, 200), font_size=14,
            anchor_x="center", anchor_y="center",
        )
        # Bottom: your info
        arcade.draw_text(
            f"{my_name} ({self.my_color})",
            WINDOW_WIDTH / 2, 20,
            (200, 200, 200), font_size=14,
            anchor_x="center", anchor_y="center",
        )

    def _draw_game_over(self):
        # Semi-transparent overlay
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT,
            (0, 0, 0, 160),
        )
        color = (100, 255, 100) if "Victoire" in self.game_result else (255, 100, 100)
        arcade.draw_text(
            self.game_result,
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 60,
            color, font_size=36,
            anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            "Lancez une revanche ou revenez au menu",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 12,
            (180, 180, 180), font_size=14,
            anchor_x="center", anchor_y="center",
        )
        self.replay_btn.draw()
        self.menu_btn.draw()
        if self.rematch_waiting:
            arcade.draw_text(
                "En attente de l'adversaire...",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 130,
                (210, 210, 220), font_size=14,
                anchor_x="center", anchor_y="center",
            )

    def _draw_round_start_countdown(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT,
            (0, 0, 0, 95),
        )

        if self.round_start_countdown > 0.0:
            value = max(1, math.ceil(self.round_start_countdown))
            pulse = 1.0 + 0.1 * math.sin(time.time() * 14.0)
            font_size = int(150 * pulse)
            text = str(value)
            color = (255, 70, 70) if value == 1 else (255, 230, 120)
        else:
            pulse = 1.0 + 0.08 * math.sin(time.time() * 18.0)
            font_size = int(110 * pulse)
            text = "FIGHT!"
            color = (255, 255, 255)

        arcade.draw_text(
            text,
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 8,
            color, font_size=font_size,
            anchor_x="center", anchor_y="center", bold=True,
        )

    # ── Update ──────────────────────────────────────────────

    def on_update(self, dt: float):
        # Update piece animations
        for piece in self.pieces:
            if piece.anim_progress < 1.0:
                piece.anim_progress = min(1.0, piece.anim_progress + dt * self.ANIM_SPEED)

        # Update capture effects
        for eff in self.capture_effects:
            eff.timer += dt
        self.capture_effects = [e for e in self.capture_effects if e.timer < e.duration]

        if self.round_start_countdown > 0.0:
            self.round_start_countdown = max(0.0, self.round_start_countdown - dt)
        elif self.round_start_fight_flash > 0.0:
            self.round_start_fight_flash = max(0.0, self.round_start_fight_flash - dt)

    # ── Input ───────────────────────────────────────────────

    def on_mouse_motion(self, x, y, dx, dy):
        self.back_btn.check_hover(x, y)
        if self.game_over:
            self.replay_btn.check_hover(x, y)
            self.menu_btn.check_hover(x, y)
        if self.dragging_piece:
            self.drag_x = x
            self.drag_y = y
            self.drag_hover_square = self._screen_to_board(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        if self.game_over:
            if button != arcade.MOUSE_BUTTON_LEFT:
                return
            if self.replay_btn.check_click(x, y):
                return
            if self.menu_btn.check_click(x, y):
                return
            return

        if self.back_btn.check_click(x, y):
            return

        if self._is_round_start_locked():
            return

        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        board_pos = self._screen_to_board(x, y)
        if board_pos is None:
            self._stop_drag()
            self._clear_selection()
            return

        row, col = board_pos
        clicked_piece = self._piece_at(row, col)

        # Select + drag own piece.
        if clicked_piece and clicked_piece.color == self.my_color:
            if self._select_piece(clicked_piece):
                self._start_drag(clicked_piece, x, y)
            return

        # Fallback: still allow click-to-move on highlighted squares.
        if self.selected_piece and (row, col) in self.valid_highlights:
            self._try_move(self.selected_piece, row, col)
            return

        self._clear_selection()

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self._is_round_start_locked() or self.game_over:
            return
        self.back_btn.check_hover(x, y)
        if self.dragging_piece:
            self.drag_x = x
            self.drag_y = y
            self.drag_hover_square = self._screen_to_board(x, y)

    def on_mouse_release(self, x, y, button, modifiers):
        if self._is_round_start_locked() or self.game_over:
            return
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if not self.dragging_piece:
            return

        piece = self.dragging_piece
        target = self._screen_to_board(x, y)
        self._stop_drag()

        if target is None:
            return

        to_row, to_col = target
        if self.selected_piece is piece and (to_row, to_col) in self.valid_highlights:
            self._try_move(piece, to_row, to_col)

    def _start_drag(self, piece: ClientPiece, x: float, y: float):
        self.dragging_piece = piece
        self.drag_x = x
        self.drag_y = y
        self.drag_hover_square = self._screen_to_board(x, y)

    def _stop_drag(self):
        self.dragging_piece = None
        self.drag_hover_square = None

    def _clear_selection(self):
        self.selected_piece = None
        self.valid_highlights.clear()

    def _request_rematch(self):
        if self.rematch_waiting:
            return
        self.rematch_waiting = True
        self.replay_btn.enabled = False
        self.replay_btn.text = "En attente..."
        socket_client.emit("game:rematch_request")

    def _select_piece(self, piece: ClientPiece) -> bool:
        if piece.is_on_cooldown():
            return False
        self.selected_piece = piece
        # Client-side move highlighting (basic — server validates)
        self.valid_highlights = self._get_basic_moves(piece)
        return True

    def _get_basic_moves(self, piece: ClientPiece) -> list[tuple[int, int]]:
        """Compute basic valid squares for highlighting (simplified client-side)."""
        moves = []
        for r in range(8):
            for c in range(8):
                if r == piece.row and c == piece.col:
                    continue
                target = self._piece_at(r, c)
                if target and target.color == piece.color:
                    continue
                if self._basic_valid(piece, r, c, target):
                    moves.append((r, c))
        return moves

    def _basic_valid(self, piece: ClientPiece, to_r: int, to_c: int, target: ClientPiece | None) -> bool:
        dr = to_r - piece.row
        dc = to_c - piece.col

        match piece.piece_type:
            case "pawn":
                direction = 1 if piece.color == "white" else -1
                start_row = 1 if piece.color == "white" else 6
                if dc == 0 and dr == direction and target is None:
                    return True
                if dc == 0 and dr == 2 * direction and piece.row == start_row and target is None:
                    return self._piece_at(piece.row + direction, piece.col) is None
                if abs(dc) == 1 and dr == direction and target is not None:
                    return True
                # En passant
                if (abs(dc) == 1 and dr == direction and target is None
                        and self.en_passant_square == (to_r, to_c)):
                    return True
            case "knight":
                return (abs(dr), abs(dc)) in ((2, 1), (1, 2))
            case "bishop":
                if abs(dr) == abs(dc) and dr != 0:
                    return self._path_clear(piece, dr, dc)
            case "rook":
                if (dr == 0) != (dc == 0):
                    return self._path_clear(piece, dr, dc)
            case "queen":
                if abs(dr) == abs(dc) and dr != 0:
                    return self._path_clear(piece, dr, dc)
                if (dr == 0) != (dc == 0):
                    return self._path_clear(piece, dr, dc)
            case "king":
                if abs(dr) <= 1 and abs(dc) <= 1:
                    return True
                # Castling
                if dr == 0 and abs(dc) == 2:
                    return self._can_castle_client(piece, dc)
        return False

    def _can_castle_client(self, king: ClientPiece, dc: int) -> bool:
        """Client-side castling check for move highlighting."""
        if king.last_move_time != 0.0:
            return False
        rook_col = 7 if dc > 0 else 0
        path_cols = range(5, 7) if dc > 0 else range(1, 4)
        rook = self._piece_at(king.row, rook_col)
        if rook is None or rook.piece_type != "rook" or rook.color != king.color:
            return False
        if rook.last_move_time != 0.0:
            return False
        return all(self._piece_at(king.row, c) is None for c in path_cols)

    def _path_clear(self, piece: ClientPiece, dr: int, dc: int) -> bool:
        step_r = (1 if dr > 0 else -1) if dr != 0 else 0
        step_c = (1 if dc > 0 else -1) if dc != 0 else 0
        steps = max(abs(dr), abs(dc))
        for i in range(1, steps):
            r = piece.row + step_r * i
            c = piece.col + step_c * i
            if self._piece_at(r, c) is not None:
                return False
        return True

    def _can_attack_local(self, attacker: ClientPiece, to_r: int, to_c: int) -> bool:
        """Can *attacker* reach (to_r, to_c)? Used for check detection (no castling/EP)."""
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

    def _is_in_check_local(self, color: str) -> bool:
        """Return True if the king of *color* is attacked by any opponent piece."""
        king = next((p for p in self.pieces if p.alive and p.piece_type == "king" and p.color == color), None)
        if not king:
            return False
        opp = "black" if color == "white" else "white"
        for p in self.pieces:
            if p.alive and p.color == opp and self._can_attack_local(p, king.row, king.col):
                return True
        return False

    def _find_attackers(self, king_color: str) -> list[ClientPiece]:
        """Return opponent pieces currently attacking the king of *king_color*."""
        king = next((p for p in self.pieces if p.alive and p.piece_type == "king" and p.color == king_color), None)
        if not king:
            return []
        opp = "black" if king_color == "white" else "white"
        return [p for p in self.pieces if p.alive and p.color == opp and self._can_attack_local(p, king.row, king.col)]

    def _try_move(self, piece: ClientPiece, to_row: int, to_col: int):
        """Send move to server and optimistically animate."""
        if self._is_round_start_locked():
            return
        if piece.is_on_cooldown() or self.pending_move is not None:
            return
        if (to_row, to_col) not in self.valid_highlights:
            return

        # Optimistic animation
        old_x, old_y = self._board_to_screen(piece.row, piece.col)
        piece.anim_from_x = old_x
        piece.anim_from_y = old_y
        piece.anim_progress = 0.0

        from_row, from_col = piece.row, piece.col
        piece.row = to_row
        piece.col = to_col

        self.pending_move = PendingMove(
            piece=piece,
            from_row=from_row,
            from_col=from_col,
            to_row=to_row,
            to_col=to_col,
        )

        self._stop_drag()
        self._clear_selection()

        socket_client.emit("game:move", {
            "from_row": from_row,
            "from_col": from_col,
            "to_row": to_row,
            "to_col": to_col,
        })

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            if self.game_over:
                self._leave_game()
                return
            self._stop_drag()
            self._clear_selection()

    def on_text(self, text: str):
        pass
