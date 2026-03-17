from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass

import arcade

from components.button import Button
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT,
    BOARD_SIZE, SQUARE_SIZE, COOLDOWNS, SPRITES_DIR,
)
from utils.socket_client import socket_client


# ── Rumble layout constants ──────────────────────────────────

SIDEBAR_WIDTH = 180
RUMBLE_BOARD_PIXEL = BOARD_SIZE * SQUARE_SIZE  # 640
RUMBLE_BOARD_OFFSET_X = SIDEBAR_WIDTH + (WINDOW_WIDTH - 2 * SIDEBAR_WIDTH - RUMBLE_BOARD_PIXEL) // 2
RUMBLE_BOARD_OFFSET_Y = (WINDOW_HEIGHT - RUMBLE_BOARD_PIXEL) // 2

# Rumble board colors (distinct from standard)
RUMBLE_LIGHT = (200, 190, 220)
RUMBLE_DARK = (110, 90, 140)
HIGHLIGHT_COLOR = (255, 200, 50, 90)

GOLD = [(180, 150, 50), (210, 175, 60), (240, 200, 80), (255, 220, 100)]


@dataclass
class RumblePiece:
    piece_type: str
    color: str
    row: int
    col: int
    alive: bool = True
    cooldown_remaining: float = 0.0
    cooldown_total: float = 0.0
    last_move_time: float = 0.0
    piece_id: int = 0
    tags: dict = None

    # Animation
    anim_from_x: float | None = None
    anim_from_y: float | None = None
    anim_progress: float = 1.0

    def __post_init__(self):
        if self.tags is None:
            self.tags = {}

    @property
    def sprite_name(self) -> str:
        return f"{self.color}_{self.piece_type}"

    def is_on_cooldown(self) -> bool:
        if self.last_move_time == 0.0:
            return False
        return (time.time() - self.last_move_time) < self.cooldown_total

    def remaining_cd(self) -> float:
        if self.last_move_time == 0.0:
            return 0.0
        return max(0.0, self.cooldown_total - (time.time() - self.last_move_time))

    def cd_fraction(self) -> float:
        if self.cooldown_total <= 0:
            return 0.0
        return self.remaining_cd() / self.cooldown_total

    def is_stunned(self) -> bool:
        return self.tags.get("stun_until", 0) > time.time()


@dataclass
class CaptureEffect:
    x: float
    y: float
    timer: float = 0.0
    duration: float = 0.4


@dataclass
class PendingMove:
    piece: RumblePiece
    from_row: int
    from_col: int
    to_row: int
    to_col: int


class RumbleGameScreen:
    """The Rumble mode game screen with sidebars, score diamond, and augment activation."""

    ANIM_SPEED = 8.0
    ROUND_START_COUNTDOWN = 3.0
    ROUND_START_FIGHT_FLASH = 0.55

    def __init__(self, window: arcade.Window):
        self.window = window
        self.my_color: str = "white"
        self.opponent_name: str = ""
        self.pieces: list[RumblePiece] = []
        self.entities: list[dict] = []  # board entities (duck, trap, wall)
        self.selected_piece: RumblePiece | None = None
        self.valid_highlights: list[tuple[int, int]] = []
        self.dragging_piece: RumblePiece | None = None
        self.drag_x: float = 0.0
        self.drag_y: float = 0.0
        self.drag_hover_square: tuple[int, int] | None = None
        self.pending_move: PendingMove | None = None
        self.capture_effects: list[CaptureEffect] = []
        self.en_passant_square: tuple[int, int] | None = None

        self.round_start_countdown = self.ROUND_START_COUNTDOWN
        self.round_start_fight_flash = self.ROUND_START_FIGHT_FLASH

        self.round_num: int = 1
        self.scores: dict = {"white": 0, "black": 0}
        self.my_augments: list[dict] = []
        self.opp_augments: list[dict] = []
        self.round_over: bool = False
        self.round_result: str = ""
        self.match_over: bool = False
        self.match_result: str = ""

        # Augment activation state
        self.augment_keybinds: dict[str, str] = {}  # key_char -> augment_id
        self.targeting_augment: str | None = None  # augment_id waiting for target click
        self.activation_cds: dict[str, float] = {}  # augment_id -> last_activation

        self.sprite_cache: dict[str, arcade.Texture] = {}
        self._sprite_list = arcade.SpriteList()

        self.back_btn = Button(
            80, WINDOW_HEIGHT - 25, 100, 30, "← Quitter",
            on_click=self._leave_game, color=(80, 40, 40), font_size=12,
        )

        self._register_socket_events()

    def _register_socket_events(self):
        socket_client.on("rumble:move_ack", self._on_move_ack)
        socket_client.on("rumble:opponent_move", self._on_opponent_move)
        socket_client.on("rumble:round_over", self._on_round_over)
        socket_client.on("rumble:activate_ack", self._on_activate_ack)
        socket_client.on("rumble:augment_activated", self._on_augment_activated)
        socket_client.on("rumble:augment_phase", self._on_augment_phase)

    def on_show(self):
        data = getattr(self.window, "rumble_round_data", None)
        if not data:
            return
        self._clear_selection()
        self._stop_drag()
        self.pending_move = None
        self.capture_effects.clear()
        self.round_over = False
        self.round_result = ""
        self.match_over = False
        self.match_result = ""
        self.en_passant_square = None
        self.targeting_augment = None
        self.round_start_countdown = self.ROUND_START_COUNTDOWN
        self.round_start_fight_flash = self.ROUND_START_FIGHT_FLASH

        self.my_color = data.get("your_color", "white")
        self.opponent_name = data.get("black") if self.my_color == "white" else data.get("white")
        self.round_num = data.get("round", 1)
        self.scores = data.get("scores", {"white": 0, "black": 0})
        self.my_augments = data.get("my_augments", [])
        self.opp_augments = data.get("opponent_augments", [])
        self.entities = data.get("entities", [])

        self._load_state(data.get("state", []))
        self._load_sprites()
        self._process_effects(data.get("effects", []))
        self._assign_keybinds()

    def _is_round_start_locked(self) -> bool:
        return self.round_start_countdown > 0.0 or self.round_start_fight_flash > 0.0

    def _load_state(self, state: list[dict]):
        self.pieces.clear()
        for p in state:
            self.pieces.append(RumblePiece(
                piece_type=p["type"],
                color=p["color"],
                row=p["row"],
                col=p["col"],
                alive=p.get("alive", True),
                cooldown_remaining=p.get("cooldown_remaining", 0.0),
                cooldown_total=COOLDOWNS.get(p["type"], 1.0),
                piece_id=p.get("piece_id", 0),
                tags=p.get("tags", {}),
            ))

    def _load_sprites(self):
        for name in [
            "white_king", "white_queen", "white_bishop", "white_knight", "white_rook", "white_pawn",
            "black_king", "black_queen", "black_bishop", "black_knight", "black_rook", "black_pawn",
        ]:
            if name in self.sprite_cache:
                continue
            path = os.path.join(SPRITES_DIR, f"{name}.png")
            if os.path.exists(path):
                self.sprite_cache[name] = arcade.load_texture(path)

    def _assign_keybinds(self):
        """Auto-assign number keys 1-9 to activable augments."""
        self.augment_keybinds.clear()
        keys = "123456789"
        idx = 0
        for aug in self.my_augments:
            if aug.get("is_activable") and idx < len(keys):
                self.augment_keybinds[keys[idx]] = aug["id"]
                idx += 1

    # ── Coordinate conversion (Rumble layout) ────────────────

    def _board_to_screen(self, row: int, col: int) -> tuple[float, float]:
        if self.my_color == "black":
            row, col = 7 - row, 7 - col
        x = RUMBLE_BOARD_OFFSET_X + col * SQUARE_SIZE + SQUARE_SIZE / 2
        y = RUMBLE_BOARD_OFFSET_Y + row * SQUARE_SIZE + SQUARE_SIZE / 2
        return x, y

    def _screen_to_board(self, sx: float, sy: float) -> tuple[int, int] | None:
        col = int((sx - RUMBLE_BOARD_OFFSET_X) / SQUARE_SIZE)
        row = int((sy - RUMBLE_BOARD_OFFSET_Y) / SQUARE_SIZE)
        if self.my_color == "black":
            row, col = 7 - row, 7 - col
        if 0 <= row < 8 and 0 <= col < 8:
            return row, col
        return None

    def _piece_at(self, row: int, col: int) -> RumblePiece | None:
        for p in self.pieces:
            if p.alive and p.row == row and p.col == col:
                return p
        return None

    # ── Socket handlers ──────────────────────────────────────

    def _on_move_ack(self, data):
        if not data.get("ok"):
            if self.pending_move:
                piece = self.pending_move.piece
                if piece.alive:
                    piece.row = self.pending_move.from_row
                    piece.col = self.pending_move.from_col
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
        cr = data.get("castling_rook")
        if cr:
            self._apply_castling_rook(cr)
        ep = data.get("en_passant_square")
        self.en_passant_square = tuple(ep) if ep else None

        if data.get("opponent_king_in_check"):
            opp_color = "black" if self.my_color == "white" else "white"
            for p in self.pieces:
                if p.alive and p.piece_type == "king" and p.color == opp_color:
                    p.last_move_time = 0.0
                    break

        self._process_effects(data.get("effects", []))

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

        if data.get("captured"):
            self._apply_capture(data["captured"])
        cr = data.get("castling_rook")
        if cr:
            self._apply_castling_rook(cr)
        ep = data.get("en_passant_square")
        self.en_passant_square = tuple(ep) if ep else None

        if data.get("my_king_in_check"):
            for p in self.pieces:
                if p.alive and p.piece_type == "king" and p.color == self.my_color:
                    p.last_move_time = 0.0
                    break

        self._process_effects(data.get("effects", []))

    def _apply_castling_rook(self, cr):
        rook = self._piece_at(cr["row"], cr["from_col"])
        if rook:
            old_x, old_y = self._board_to_screen(rook.row, rook.col)
            rook.anim_from_x = old_x
            rook.anim_from_y = old_y
            rook.anim_progress = 0.0
            rook.col = cr["to_col"]

    def _apply_capture(self, cap):
        for p in self.pieces:
            if (p.alive and p.row == cap["row"] and p.col == cap["col"]
                    and p.color == cap["color"] and p.piece_type == cap["type"]):
                p.alive = False
                sx, sy = self._board_to_screen(p.row, p.col)
                self.capture_effects.append(CaptureEffect(x=sx, y=sy))
                break

    def _on_round_over(self, data):
        self.round_over = True
        winner = data.get("round_winner", "")
        self.scores = data.get("scores", self.scores)
        self.match_over = data.get("match_over", False)

        if self.match_over:
            mw = data.get("match_winner", "")
            if mw == self.my_color:
                self.match_result = "VICTOIRE DU MATCH !"
            else:
                self.match_result = "DÉFAITE DU MATCH..."
            if data.get("reason") == "opponent_disconnected":
                self.match_result += " (déconnexion)"
        else:
            if winner == self.my_color:
                self.round_result = "Manche gagnée !"
            else:
                self.round_result = "Manche perdue..."

    def _on_activate_ack(self, data):
        if data.get("ok"):
            aug_id = data.get("augment_id", "")
            self.activation_cds[aug_id] = time.time()
            self._process_effects(data.get("effects", []))
        self.targeting_augment = None

    def _on_augment_activated(self, data):
        self._process_effects(data.get("effects", []))

    def _on_augment_phase(self, data):
        self.window.rumble_augment_data = data
        self.window.show_screen("augment_select")

    def _process_effects(self, effects: list[dict]):
        """Process visual effects from augments."""
        for fx in effects:
            fx_type = fx.get("type", "")
            if fx_type == "capture":
                self._apply_capture(fx)
            elif fx_type == "spawn":
                self.pieces.append(RumblePiece(
                    piece_type=fx["piece_type"], color=fx["color"],
                    row=fx["row"], col=fx["col"],
                    cooldown_total=COOLDOWNS.get(fx["piece_type"], 1.0),
                    last_move_time=time.time(),
                    piece_id=fx.get("piece_id", 0),
                ))
            elif fx_type == "transform":
                pid = fx.get("piece_id", 0)
                for p in self.pieces:
                    if p.piece_id == pid:
                        p.tags["transformed"] = fx.get("visual", "")
                        break
            elif fx_type == "stun":
                pid = fx.get("piece_id", 0)
                dur = fx.get("duration", 3.0)
                for p in self.pieces:
                    if p.piece_id == pid:
                        p.tags["stun_until"] = time.time() + dur
                        break
            elif fx_type == "teleport":
                pid = fx.get("piece_id", 0)
                for p in self.pieces:
                    if p.piece_id == pid:
                        old_x, old_y = self._board_to_screen(p.row, p.col)
                        p.anim_from_x = old_x
                        p.anim_from_y = old_y
                        p.anim_progress = 0.0
                        p.row = fx["to_row"]
                        p.col = fx["to_col"]
                        break
            elif fx_type == "swap":
                p1_id = fx.get("piece1_id", 0)
                p2_id = fx.get("piece2_id", 0)
                for p in self.pieces:
                    if p.piece_id == p1_id:
                        old_x, old_y = self._board_to_screen(p.row, p.col)
                        p.anim_from_x = old_x
                        p.anim_from_y = old_y
                        p.anim_progress = 0.0
                        p.row = fx["p1_row"]
                        p.col = fx["p1_col"]
                    elif p.piece_id == p2_id:
                        old_x, old_y = self._board_to_screen(p.row, p.col)
                        p.anim_from_x = old_x
                        p.anim_from_y = old_y
                        p.anim_progress = 0.0
                        p.row = fx["p2_row"]
                        p.col = fx["p2_col"]
            elif fx_type == "duck_place":
                # Remove old duck from same owner
                self.entities = [e for e in self.entities
                                 if not (e.get("type") == "duck" and e.get("owner") == fx.get("color"))]
                self.entities.append({"type": "duck", "row": fx["row"], "col": fx["col"],
                                      "owner": fx.get("color", "")})
            elif fx_type == "trap_place":
                if fx.get("color") == self.my_color:
                    self.entities.append({"type": "trap", "row": fx["row"], "col": fx["col"],
                                          "owner": fx["color"]})
            elif fx_type == "trap_trigger":
                self.entities = [e for e in self.entities
                                 if not (e.get("type") == "trap"
                                         and e["row"] == fx["row"] and e["col"] == fx["col"])]
            elif fx_type == "corruption":
                pid = fx.get("piece_id", 0)
                for p in self.pieces:
                    if p.piece_id == pid:
                        p.color = fx.get("new_color", p.color)
                        p.last_move_time = time.time()
                        break
            elif fx_type == "shadow_clone":
                self.pieces.append(RumblePiece(
                    piece_type=fx["piece_type"], color=fx["color"],
                    row=fx["row"], col=fx["col"],
                    cooldown_total=COOLDOWNS.get(fx["piece_type"], 1.0),
                    last_move_time=time.time(),
                    piece_id=fx.get("piece_id", 0),
                    tags={"is_clone": True},
                ))
            elif fx_type in ("meteor_warning", "meteor_impact"):
                sx, sy = self._board_to_screen(fx["row"], fx["col"])
                self.capture_effects.append(CaptureEffect(x=sx, y=sy, duration=0.6))

    def _leave_game(self):
        socket_client.emit("rumble:leave_room")
        self.window.show_screen("home")

    # ── Drawing ──────────────────────────────────────────────

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )
        self._draw_board()
        self._draw_entities()
        self._draw_highlights()
        self._draw_pieces()
        self._draw_capture_effects()
        self._draw_left_sidebar()
        self._draw_right_sidebar()
        self._draw_top_bar()

        if self._is_round_start_locked() and not self.round_over:
            self._draw_round_start_countdown()
        if self.round_over:
            self._draw_round_over()

    def _draw_board(self):
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                x, y = self._board_to_screen(row, col)
                is_light = (row + col) % 2 == 0
                color = RUMBLE_DARK if is_light else RUMBLE_LIGHT
                arcade.draw_rectangle_filled(x, y, SQUARE_SIZE, SQUARE_SIZE, color)
        bx = RUMBLE_BOARD_OFFSET_X + RUMBLE_BOARD_PIXEL / 2
        by = RUMBLE_BOARD_OFFSET_Y + RUMBLE_BOARD_PIXEL / 2
        arcade.draw_rectangle_outline(bx, by, RUMBLE_BOARD_PIXEL, RUMBLE_BOARD_PIXEL, (140, 100, 180), 3)

    def _draw_entities(self):
        """Draw ducks, traps (own), and walls."""
        for ent in self.entities:
            r, c = ent["row"], ent["col"]
            x, y = self._board_to_screen(r, c)
            if ent["type"] == "duck":
                arcade.draw_circle_filled(x, y, SQUARE_SIZE * 0.3, (255, 220, 50))
                arcade.draw_text("D", x, y, (80, 60, 0), font_size=16,
                                 anchor_x="center", anchor_y="center", bold=True)
            elif ent["type"] == "trap" and ent.get("owner") == self.my_color:
                arcade.draw_rectangle_filled(x, y, SQUARE_SIZE * 0.5, SQUARE_SIZE * 0.5, (200, 50, 50, 100))
                arcade.draw_text("T", x, y, (255, 100, 100, 150), font_size=12,
                                 anchor_x="center", anchor_y="center")
            elif ent["type"] == "wall":
                arcade.draw_rectangle_filled(x, y, SQUARE_SIZE * 0.8, SQUARE_SIZE * 0.8, (100, 100, 110))

    def _draw_highlights(self):
        pulse = 0.5 + 0.5 * math.sin(time.time() * 7.0)
        for row, col in self.valid_highlights:
            x, y = self._board_to_screen(row, col)
            arcade.draw_rectangle_filled(x, y, SQUARE_SIZE, SQUARE_SIZE, HIGHLIGHT_COLOR)
            outer_r = SQUARE_SIZE * (0.16 + 0.03 * pulse)
            arcade.draw_circle_filled(x, y, outer_r, (255, 245, 180, 45))

        if self.drag_hover_square and self.drag_hover_square in self.valid_highlights:
            row, col = self.drag_hover_square
            x, y = self._board_to_screen(row, col)
            arcade.draw_rectangle_outline(x, y, SQUARE_SIZE * 0.88, SQUARE_SIZE * 0.88, (255, 245, 190, 220), 3)

        if self.selected_piece:
            x, y = self._board_to_screen(self.selected_piece.row, self.selected_piece.col)
            arcade.draw_rectangle_filled(x, y, SQUARE_SIZE, SQUARE_SIZE, (100, 200, 100, 80))

        # Targeting mode highlight
        if self.targeting_augment:
            arcade.draw_text(
                "Cliquez sur une cible...", WINDOW_WIDTH / 2, 15,
                (255, 200, 50), font_size=12, anchor_x="center", anchor_y="center",
            )

    def _draw_pieces(self):
        dragged = self.dragging_piece if self.dragging_piece and self.dragging_piece.alive else None
        for piece in self.pieces:
            if not piece.alive or piece is dragged:
                continue
            target_x, target_y = self._board_to_screen(piece.row, piece.col)
            if piece.anim_progress < 1.0:
                ax = piece.anim_from_x or target_x
                ay = piece.anim_from_y or target_y
                t = piece.anim_progress
                draw_x = ax + (target_x - ax) * t
                draw_y = ay + (target_y - ay) * t
            else:
                draw_x = target_x
                draw_y = target_y

            is_mine = piece.color == self.my_color
            on_cd = piece.is_on_cooldown()
            stunned = piece.is_stunned()
            alpha = 100 if stunned else (140 if (is_mine and on_cd) else 255)

            self._draw_piece_visual(piece, draw_x, draw_y, alpha)

            if on_cd:
                self._draw_cooldown_indicator(piece, draw_x, draw_y, is_mine)
            if stunned:
                arcade.draw_text("STUN", draw_x, draw_y + SQUARE_SIZE * 0.35,
                                 (255, 50, 50), font_size=8, anchor_x="center", bold=True)
            # Transformed badge
            transformed = piece.tags.get("transformed", "")
            if transformed:
                arcade.draw_text(transformed[:3].upper(), draw_x, draw_y - SQUARE_SIZE * 0.38,
                                 (200, 180, 255), font_size=7, anchor_x="center", bold=True)

        if dragged:
            self._draw_piece_visual(dragged, self.drag_x, self.drag_y, 245, size_mult=1.08)

    def _draw_piece_visual(self, piece, x, y, alpha, size_mult=1.0):
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
            symbols = {
                ("white", "king"): "K", ("white", "queen"): "Q",
                ("white", "rook"): "R", ("white", "bishop"): "B",
                ("white", "knight"): "N", ("white", "pawn"): "P",
                ("black", "king"): "k", ("black", "queen"): "q",
                ("black", "rook"): "r", ("black", "bishop"): "b",
                ("black", "knight"): "n", ("black", "pawn"): "p",
            }
            sym = symbols.get((piece.color, piece.piece_type), "?")
            bg = (240, 240, 240, alpha) if piece.color == "white" else (50, 50, 50, alpha)
            fg = (30, 30, 30, alpha) if piece.color == "white" else (230, 230, 230, alpha)
            r = SQUARE_SIZE * 0.35 * size_mult
            arcade.draw_circle_filled(x, y, r, bg)
            arcade.draw_circle_outline(x, y, r, (0, 0, 0, 100), 2)
            arcade.draw_text(sym, x, y, fg, font_size=int(22 * size_mult),
                             anchor_x="center", anchor_y="center", bold=True)

    def _draw_cooldown_indicator(self, piece, x, y, is_mine):
        frac = piece.cd_fraction()
        if frac <= 0:
            return
        if is_mine:
            radius = SQUARE_SIZE * 0.4
            segments = 24
            angle_end = 360 * frac
            points = [(x, y)]
            for i in range(segments + 1):
                a = 90 - (angle_end * i / segments)
                rad = math.radians(a)
                points.append((x + radius * math.cos(rad), y + radius * math.sin(rad)))
            if len(points) >= 3:
                arcade.draw_polygon_filled(points, (200, 60, 60, 80))
        else:
            remaining = piece.remaining_cd()
            if remaining > 0:
                bx = x + SQUARE_SIZE * 0.3
                by = y + SQUARE_SIZE * 0.35
                arcade.draw_circle_filled(bx, by, 12, (200, 50, 50, 200))
                arcade.draw_text(f"{remaining:.1f}", bx, by, (255, 255, 255), font_size=8,
                                 anchor_x="center", anchor_y="center", bold=True)

    def _draw_capture_effects(self):
        for eff in self.capture_effects:
            t = eff.timer / eff.duration
            alpha = int(255 * (1.0 - t))
            radius = 20 + 30 * t
            arcade.draw_circle_filled(eff.x, eff.y, radius, (255, 100, 50, alpha))

    def _draw_left_sidebar(self):
        """Draw player's profile and augments."""
        arcade.draw_rectangle_filled(SIDEBAR_WIDTH / 2, WINDOW_HEIGHT / 2,
                                     SIDEBAR_WIDTH, WINDOW_HEIGHT, (35, 30, 45))
        user = getattr(self.window, "user_data", None)
        name = user["username"] if user else "Vous"
        arcade.draw_text(name, SIDEBAR_WIDTH / 2, WINDOW_HEIGHT - 20,
                         (200, 200, 210), font_size=12, anchor_x="center", bold=True)
        arcade.draw_text(f"({self.my_color})", SIDEBAR_WIDTH / 2, WINDOW_HEIGHT - 38,
                         (150, 150, 160), font_size=10, anchor_x="center")

        arcade.draw_text("Augments actifs", SIDEBAR_WIDTH / 2, WINDOW_HEIGHT - 65,
                         (255, 200, 80), font_size=10, anchor_x="center", bold=True)

        # Keybind mapping (reversed)
        id_to_key = {v: k for k, v in self.augment_keybinds.items()}

        for i, aug in enumerate(self.my_augments):
            y = WINDOW_HEIGHT - 90 - i * 38
            if y < 30:
                break
            aug_id = aug.get("id", "")
            key = id_to_key.get(aug_id, "")
            key_str = f"[{key}] " if key else ""

            # Activation CD display
            if aug.get("is_activable"):
                last = self.activation_cds.get(aug_id, 0)
                cd = aug.get("cooldown", 0)
                remaining = max(0, cd - (time.time() - last)) if last > 0 else 0
                if remaining > 0:
                    color = (150, 80, 80)
                    suffix = f" ({remaining:.0f}s)"
                else:
                    color = (180, 160, 100)
                    suffix = ""
            else:
                color = (150, 150, 160)
                suffix = ""

            arcade.draw_text(
                f"{key_str}{aug.get('name', '?')}{suffix}",
                10, y, color, font_size=9, bold=bool(key),
            )

    def _draw_right_sidebar(self):
        """Draw opponent's profile and augments."""
        sx = WINDOW_WIDTH - SIDEBAR_WIDTH / 2
        arcade.draw_rectangle_filled(sx, WINDOW_HEIGHT / 2,
                                     SIDEBAR_WIDTH, WINDOW_HEIGHT, (35, 30, 45))
        arcade.draw_text(self.opponent_name or "Adversaire", sx, WINDOW_HEIGHT - 20,
                         (200, 200, 210), font_size=12, anchor_x="center", bold=True)
        opp_color = "black" if self.my_color == "white" else "white"
        arcade.draw_text(f"({opp_color})", sx, WINDOW_HEIGHT - 38,
                         (150, 150, 160), font_size=10, anchor_x="center")

        arcade.draw_text("Augments actifs", sx, WINDOW_HEIGHT - 65,
                         (255, 200, 80), font_size=10, anchor_x="center", bold=True)

        for i, aug in enumerate(self.opp_augments):
            y = WINDOW_HEIGHT - 90 - i * 38
            if y < 30:
                break
            color = (180, 160, 100) if aug.get("is_activable") else (150, 150, 160)
            arcade.draw_text(aug.get("name", "?"), WINDOW_WIDTH - SIDEBAR_WIDTH + 10, y,
                             color, font_size=9)

    def _draw_top_bar(self):
        self.back_btn.draw()
        # Score diamond centered above board
        cx = RUMBLE_BOARD_OFFSET_X + RUMBLE_BOARD_PIXEL / 2
        cy = WINDOW_HEIGHT - 20
        self._draw_score_diamond(cx, cy)
        arcade.draw_text(
            f"Manche {self.round_num}", cx, cy - 22,
            (180, 180, 190), font_size=10, anchor_x="center", anchor_y="center",
        )

    def _draw_score_diamond(self, cx, cy):
        size = 12
        gap = 2
        for player_color, offset_y in [(self.my_color, -(size + gap)), ("black" if self.my_color == "white" else "white", size + gap)]:
            score = self.scores.get(player_color, 0)
            for i in range(4):
                sx = cx - (1.5 * (size + gap)) + i * (size + gap)
                sy = cy + offset_y
                fill = GOLD[min(i, 3)] if i < score else (60, 60, 70)
                arcade.draw_rectangle_filled(sx, sy, size, size, fill)
                arcade.draw_rectangle_outline(sx, sy, size, size, (120, 120, 130), 1)

    def _draw_round_start_countdown(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, WINDOW_WIDTH, WINDOW_HEIGHT, (0, 0, 0, 95),
        )
        if self.round_start_countdown > 0.0:
            value = max(1, math.ceil(self.round_start_countdown))
            pulse = 1.0 + 0.1 * math.sin(time.time() * 14.0)
            font_size = int(150 * pulse)
            color = (255, 70, 70) if value == 1 else (255, 230, 120)
            arcade.draw_text(str(value), WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 8,
                             color, font_size=font_size, anchor_x="center", anchor_y="center", bold=True)
        else:
            pulse = 1.0 + 0.08 * math.sin(time.time() * 18.0)
            arcade.draw_text("FIGHT!", WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 8,
                             (255, 255, 255), font_size=int(110 * pulse),
                             anchor_x="center", anchor_y="center", bold=True)

    def _draw_round_over(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, WINDOW_WIDTH, WINDOW_HEIGHT, (0, 0, 0, 170),
        )
        if self.match_over:
            color = (100, 255, 100) if "VICTOIRE" in self.match_result else (255, 100, 100)
            arcade.draw_text(self.match_result, WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 30,
                             color, font_size=30, anchor_x="center", anchor_y="center", bold=True)
            arcade.draw_text(
                f"Score: {self.scores.get('white', 0)} - {self.scores.get('black', 0)}",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 20,
                (200, 200, 210), font_size=16, anchor_x="center", anchor_y="center",
            )
            arcade.draw_text(
                "Appuyez sur Échap pour quitter", WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 60,
                (150, 150, 160), font_size=12, anchor_x="center", anchor_y="center",
            )
        else:
            color = (100, 255, 100) if "gagnée" in self.round_result else (255, 100, 100)
            arcade.draw_text(self.round_result, WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 20,
                             color, font_size=26, anchor_x="center", anchor_y="center", bold=True)
            arcade.draw_text(
                f"Score: {self.scores.get('white', 0)} - {self.scores.get('black', 0)}",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 20,
                (200, 200, 210), font_size=14, anchor_x="center", anchor_y="center",
            )
            arcade.draw_text(
                "Prochaine manche...", WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 55,
                (180, 180, 190), font_size=13, anchor_x="center", anchor_y="center",
            )

    # ── Update ───────────────────────────────────────────────

    def on_update(self, dt: float):
        for piece in self.pieces:
            if piece.anim_progress < 1.0:
                piece.anim_progress = min(1.0, piece.anim_progress + dt * self.ANIM_SPEED)
        for eff in self.capture_effects:
            eff.timer += dt
        self.capture_effects = [e for e in self.capture_effects if e.timer < e.duration]

        if self.round_start_countdown > 0.0:
            self.round_start_countdown = max(0.0, self.round_start_countdown - dt)
        elif self.round_start_fight_flash > 0.0:
            self.round_start_fight_flash = max(0.0, self.round_start_fight_flash - dt)

    # ── Input ────────────────────────────────────────────────

    def on_mouse_motion(self, x, y, dx, dy):
        self.back_btn.check_hover(x, y)
        if self.dragging_piece:
            self.drag_x = x
            self.drag_y = y
            self.drag_hover_square = self._screen_to_board(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        if self.round_over:
            if self.match_over:
                return
            return

        if self.back_btn.check_click(x, y):
            return
        if self._is_round_start_locked():
            return
        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        board_pos = self._screen_to_board(x, y)

        # Targeting mode for augment activation
        if self.targeting_augment and board_pos:
            row, col = board_pos
            socket_client.emit("rumble:activate", {
                "augment_id": self.targeting_augment,
                "target_row": row, "target_col": col,
            })
            self.targeting_augment = None
            return

        if board_pos is None:
            self._stop_drag()
            self._clear_selection()
            return

        row, col = board_pos
        clicked = self._piece_at(row, col)

        if clicked and clicked.color == self.my_color:
            if self._select_piece(clicked):
                self._start_drag(clicked, x, y)
            return

        if self.selected_piece and (row, col) in self.valid_highlights:
            self._try_move(self.selected_piece, row, col)
            return

        self._clear_selection()

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self._is_round_start_locked() or self.round_over:
            return
        self.back_btn.check_hover(x, y)
        if self.dragging_piece:
            self.drag_x = x
            self.drag_y = y
            self.drag_hover_square = self._screen_to_board(x, y)

    def on_mouse_release(self, x, y, button, modifiers):
        if self._is_round_start_locked() or self.round_over:
            return
        if button != arcade.MOUSE_BUTTON_LEFT or not self.dragging_piece:
            return

        piece = self.dragging_piece
        target = self._screen_to_board(x, y)
        self._stop_drag()

        if target and self.selected_piece is piece and target in self.valid_highlights:
            self._try_move(piece, target[0], target[1])

    def _start_drag(self, piece, x, y):
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

    def _select_piece(self, piece) -> bool:
        if piece.is_on_cooldown() or piece.is_stunned():
            return False
        if piece.tags.get("is_wall"):
            return False
        self.selected_piece = piece
        self.valid_highlights = self._get_basic_moves(piece)
        return True

    def _get_basic_moves(self, piece) -> list[tuple[int, int]]:
        """Client-side basic move computation for highlighting."""
        moves = []
        for r in range(8):
            for c in range(8):
                if r == piece.row and c == piece.col:
                    continue
                target = self._piece_at(r, c)
                if target and target.color == piece.color:
                    continue
                # Check entity blocking
                blocked = False
                for ent in self.entities:
                    if ent["row"] == r and ent["col"] == c and ent["type"] in ("duck", "wall"):
                        blocked = True
                        break
                if blocked:
                    continue
                if self._basic_valid(piece, r, c, target):
                    moves.append((r, c))
        return moves

    def _basic_valid(self, piece, to_r, to_c, target) -> bool:
        dr = to_r - piece.row
        dc = to_c - piece.col
        match piece.piece_type:
            case "pawn":
                direction = 1 if piece.color == "white" else -1
                start_row = 1 if piece.color == "white" else 6
                if dc == 0 and dr == direction and target is None:
                    return True
                if dc == 0 and dr == 2 * direction and (piece.row == start_row or True) and target is None:
                    # Sprinteurs: always allow 2 if path clear
                    return self._piece_at(piece.row + direction, piece.col) is None
                if abs(dc) == 1 and dr == direction and target is not None:
                    return True
                if abs(dc) == 1 and dr == direction and target is None and self.en_passant_square == (to_r, to_c):
                    return True
                # Backward (marche arriere) — simplified
                backward = -direction
                if dc == 0 and dr == backward and target is None:
                    return True
                if abs(dc) == 1 and dr == backward and target is not None:
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
                if abs(dr) <= 2 and abs(dc) <= 2:
                    return True
        return False

    def _path_clear(self, piece, dr, dc) -> bool:
        step_r = (1 if dr > 0 else -1) if dr != 0 else 0
        step_c = (1 if dc > 0 else -1) if dc != 0 else 0
        steps = max(abs(dr), abs(dc))
        for i in range(1, steps):
            r = piece.row + step_r * i
            c = piece.col + step_c * i
            if self._piece_at(r, c) is not None:
                return False
            for ent in self.entities:
                if ent["row"] == r and ent["col"] == c and ent["type"] in ("duck", "wall"):
                    return False
        return True

    def _try_move(self, piece, to_row, to_col):
        if self._is_round_start_locked():
            return
        if piece.is_on_cooldown() or piece.is_stunned() or self.pending_move is not None:
            return
        if (to_row, to_col) not in self.valid_highlights:
            return

        old_x, old_y = self._board_to_screen(piece.row, piece.col)
        piece.anim_from_x = old_x
        piece.anim_from_y = old_y
        piece.anim_progress = 0.0

        from_row, from_col = piece.row, piece.col
        piece.row = to_row
        piece.col = to_col

        self.pending_move = PendingMove(piece, from_row, from_col, to_row, to_col)
        self._stop_drag()
        self._clear_selection()

        socket_client.emit("rumble:move", {
            "from_row": from_row, "from_col": from_col,
            "to_row": to_row, "to_col": to_col,
        })

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            if self.round_over and self.match_over:
                self._leave_game()
                return
            self._stop_drag()
            self._clear_selection()
            self.targeting_augment = None
            return

        if self.round_over or self._is_round_start_locked():
            return

        # Augment activation via number keys
        char = None
        key_map = {
            arcade.key.KEY_1: "1", arcade.key.KEY_2: "2", arcade.key.KEY_3: "3",
            arcade.key.KEY_4: "4", arcade.key.KEY_5: "5", arcade.key.KEY_6: "6",
            arcade.key.KEY_7: "7", arcade.key.KEY_8: "8", arcade.key.KEY_9: "9",
        }
        char = key_map.get(key)

        if char and char in self.augment_keybinds:
            aug_id = self.augment_keybinds[char]
            # Find the augment data to check target_type
            aug_data = None
            for a in self.my_augments:
                if a.get("id") == aug_id:
                    aug_data = a
                    break
            if not aug_data:
                return

            target_type = aug_data.get("target_type", "none")
            if target_type == "none":
                socket_client.emit("rumble:activate", {"augment_id": aug_id})
            else:
                # Enter targeting mode
                self.targeting_augment = aug_id

    def on_text(self, text: str):
        pass
