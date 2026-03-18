from __future__ import annotations

import math
import time

import arcade

from components.button import Button
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT, COLOR_PRIMARY,
    COLOR_DANGER, SPRITES_DIR,
)
from utils.credentials import clear_credentials
from utils.api import api
from utils.socket_client import socket_client

import os

# ── Design tokens ─────────────────────────────────────────────────────────────
_BOARD_LIGHT = (45, 42, 55)    # subtle checker light
_BOARD_DARK  = (30, 28, 38)    # subtle checker dark
_ACCENT      = (200, 160, 60)  # gold accent
_RUMBLE_CLR  = (170, 80, 140)  # purple-pink for rumble
_CARD_BG     = (38, 36, 50, 230)
_CARD_BORDER = (80, 70, 110)
_TEXT_DIM    = (150, 145, 165)

_BUTTON_CONFIGS = [
    # (label, color, hover_color, action_key, width)
    ("⚔  Jouer - Standard",  (50, 115, 190),  (65, 135, 210),  "standard",    300),
    ("🤖  Jouer vs IA",       (45, 105, 75),   (55, 125, 90),   "ai",          300),
    ("🔥  Jouer - Rumble",    (150, 65, 115),  (175, 80, 135),  "rumble",      300),
    ("🏆  Classement",        (70, 65, 90),    (90, 85, 115),   "leaderboard", 300),
    ("👤  Mon Profil",        (70, 65, 90),    (90, 85, 115),   "profile",     300),
]


class HomeScreen:
    """Main menu after login — visually redesigned."""

    def __init__(self, window: arcade.Window):
        self.window = window
        self._t = 0.0  # animation clock

        cx = WINDOW_WIDTH / 2
        btn_y_start = WINDOW_HEIGHT / 2 + 80
        btn_gap = 60

        self.buttons: list[tuple[str, Button]] = []
        for i, (label, col, hcol, key, w) in enumerate(_BUTTON_CONFIGS):
            y = btn_y_start - i * btn_gap
            btn = Button(cx, y, w, 46, label,
                         on_click=lambda k=key: self._action(k),
                         color=col, hover_color=hcol, font_size=15)
            self.buttons.append((key, btn))

        self.logout_btn = Button(
            cx, WINDOW_HEIGHT / 2 - 240, 160, 36, "Déconnexion",
            on_click=self._logout, color=COLOR_DANGER,
            hover_color=(220, 70, 70), font_size=13,
        )

        # Piece sprites for decorative floating pieces
        self._sprite_cache: dict[str, arcade.Texture] = {}
        self._load_sprites()

        # Floating piece data: (piece_name, start_x, base_y, phase, speed, size)
        self._floaters = [
            ("white_knight", 120, 620, 0.0,    0.9, 54),
            ("black_bishop", 210, 480, 1.1,    1.1, 46),
            ("white_rook",    80, 350, 2.3,    0.7, 50),
            ("black_queen", 1090, 600, 0.5,    1.0, 58),
            ("white_pawn",  1000, 440, 1.8,    1.3, 38),
            ("black_king",  1050, 280, 3.1,    0.8, 52),
        ]

    def _load_sprites(self):
        for name in [
            "white_knight", "black_bishop", "white_rook",
            "black_queen", "white_pawn", "black_king",
            "white_king",
        ]:
            path = os.path.join(SPRITES_DIR, f"{name}.png")
            if os.path.exists(path):
                try:
                    self._sprite_cache[name] = arcade.load_texture(path)
                except Exception:
                    pass

    def _action(self, key: str):
        user = getattr(self.window, "user_data", None)
        if key == "standard":
            if user and not socket_client.connected:
                socket_client.connect(user["token"])
            self.window.show_screen("rooms")
        elif key == "ai":
            self.window.show_screen("ai_difficulty")
        elif key == "rumble":
            if user and not socket_client.connected:
                socket_client.connect(user["token"])
            self.window.show_screen("rumble_rooms")
        elif key == "leaderboard":
            self.window.show_screen("leaderboard")
        elif key == "profile":
            self.window.show_screen("profile")

    def _logout(self):
        clear_credentials()
        api.clear_token()
        socket_client.disconnect()
        self.window.user_data = None
        self.window.show_screen("login")

    # ── Drawing ───────────────────────────────────────────────────────────────

    def on_draw(self):
        t = self._t

        # ── Background: subtle animated chess pattern ─────────────────────────
        tile = 72
        for row in range(WINDOW_HEIGHT // tile + 2):
            for col in range(WINDOW_WIDTH // tile + 2):
                x = col * tile + tile / 2
                y = row * tile + tile / 2
                is_light = (row + col) % 2 == 0
                color = _BOARD_LIGHT if is_light else _BOARD_DARK
                arcade.draw_rectangle_filled(x, y, tile, tile, color)

        # ── Vignette: dark gradient from edges ────────────────────────────────
        for i, alpha in enumerate([120, 90, 60, 30]):
            margin = i * 35
            arcade.draw_rectangle_filled(
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
                WINDOW_WIDTH - margin * 2, WINDOW_HEIGHT,
                (20, 18, 28, alpha),
            )

        # ── Floating decorative pieces ────────────────────────────────────────
        sprite_list = arcade.SpriteList()
        for name, bx, by, phase, speed, size in self._floaters:
            float_y = by + 18 * math.sin(t * speed + phase)
            alpha = int(120 + 60 * math.sin(t * speed * 0.7 + phase))
            tex = self._sprite_cache.get(name)
            if tex:
                sp = arcade.Sprite(tex)
                sp.center_x = bx
                sp.center_y = float_y
                sp.width = sp.height = size
                sp.alpha = alpha
                sprite_list.append(sp)
        sprite_list.draw()

        # ── Central panel ─────────────────────────────────────────────────────
        cx = WINDOW_WIDTH / 2
        panel_h = 610
        panel_y = WINDOW_HEIGHT / 2 - 10
        arcade.draw_rectangle_filled(cx, panel_y, 400, panel_h, _CARD_BG)
        arcade.draw_rectangle_outline(cx, panel_y, 400, panel_h, _CARD_BORDER, 2)

        # Top gold accent bar
        arcade.draw_rectangle_filled(cx, panel_y + panel_h / 2 - 3, 400, 4, _ACCENT)

        # ── Logo / title ──────────────────────────────────────────────────────
        logo_y = WINDOW_HEIGHT - 80
        logo_tex = self._sprite_cache.get("white_king")
        if logo_tex:
            slist = arcade.SpriteList()
            sp = arcade.Sprite(logo_tex)
            sp.center_x = cx - 100
            sp.center_y = logo_y
            sp.width = sp.height = 44
            slist.append(sp)
            slist.draw()

        arcade.draw_text(
            "NINJA CHESS",
            cx + (24 if logo_tex else 0), logo_y + 2,
            _ACCENT, font_size=32, bold=True,
            anchor_x="center", anchor_y="center",
        )

        # Subtitle rule line
        arcade.draw_line(cx - 130, logo_y - 24, cx + 130, logo_y - 24, _CARD_BORDER, 1)
        arcade.draw_text(
            "Échecs en temps réel simultané",
            cx, logo_y - 35,
            _TEXT_DIM, font_size=11, anchor_x="center", anchor_y="center",
        )

        # ── Player info card ──────────────────────────────────────────────────
        user = getattr(self.window, "user_data", None)
        name = user["username"] if user else "Joueur"
        elo_std = user.get("elo_standard", 1000) if user else 1000
        elo_rmb = user.get("elo_rumble", 1000) if user else 1000

        info_y = WINDOW_HEIGHT - 140
        arcade.draw_rectangle_filled(cx, info_y, 340, 52, (28, 26, 40, 200))
        arcade.draw_rectangle_outline(cx, info_y, 340, 52, (70, 60, 95), 1)

        arcade.draw_text(
            name,
            cx, info_y + 12,
            COLOR_TEXT, font_size=16, bold=True,
            anchor_x="center", anchor_y="center",
        )
        arcade.draw_text(
            f"Standard  {elo_std}  •  Rumble  {elo_rmb}",
            cx, info_y - 12,
            _ACCENT, font_size=11,
            anchor_x="center", anchor_y="center",
        )

        # ── Buttons ───────────────────────────────────────────────────────────
        for _, btn in self.buttons:
            btn.draw()

        # ── Logout button ─────────────────────────────────────────────────────
        self.logout_btn.draw()

        # ── Bottom version hint ───────────────────────────────────────────────
        arcade.draw_text(
            "v0.1 — fait avec ♥ pour les amis",
            cx, 20,
            (80, 75, 100), font_size=10,
            anchor_x="center", anchor_y="center",
        )

    def on_update(self, dt: float):
        self._t += dt

    def on_mouse_motion(self, x, y, dx, dy):
        for _, btn in self.buttons:
            btn.check_hover(x, y)
        self.logout_btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        for _, btn in self.buttons:
            btn.check_click(x, y)
        self.logout_btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        pass

    def on_text(self, text: str):
        pass
