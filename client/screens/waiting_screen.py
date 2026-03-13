from __future__ import annotations

import math
import time

import arcade

from components.button import Button
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT,
)
from utils.socket_client import socket_client


class WaitingScreen:
    """Shown after creating a room — waits for a second player."""

    def __init__(self, window: arcade.Window):
        self.window = window
        self.room_name: str = ""
        self._t = 0.0

        self.cancel_btn = Button(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 140, 200, 44,
            "Annuler", on_click=self._cancel,
            color=(120, 40, 40), font_size=14,
        )
        socket_client.on("room:ready", self._on_room_ready)

    def on_show(self):
        self._t = 0.0

    def set_room(self, room_data: dict):
        self.room_name = room_data.get("name", "Room")

    def _cancel(self):
        socket_client.emit("room:leave")
        self.window.show_screen("rooms")

    def _on_room_ready(self, data):
        self.window.game_init_data = data
        self.window.show_screen("game")

    # ── Drawing ─────────────────────────────────────────────

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )

        # Title
        arcade.draw_text(
            "En attente d'un adversaire",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 120,
            COLOR_TEXT, font_size=24,
            anchor_x="center", anchor_y="center", bold=True,
        )

        # Room name
        arcade.draw_text(
            f"Room : {self.room_name}",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 70,
            (160, 160, 170), font_size=14,
            anchor_x="center", anchor_y="center",
        )

        # Your name
        user = getattr(self.window, "user_data", None)
        name = user["username"] if user else "Vous"
        elo = user.get("elo_standard", 1000) if user else 1000

        arcade.draw_text(
            f"{name}  •  Elo {elo}",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 20,
            (200, 200, 210), font_size=16,
            anchor_x="center", anchor_y="center",
        )

        # Spinner
        cx, cy = WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 40
        n = 10
        for i in range(n):
            angle = (i / n) * math.tau - self._t * 2
            alpha = int(60 + 195 * (i / (n - 1)))
            r = 28
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            arcade.draw_circle_filled(x, y, 5, (100, 160, 240, alpha))

        self.cancel_btn.draw()

    def on_update(self, dt: float):
        self._t += dt

    def on_mouse_motion(self, x, y, dx, dy):
        self.cancel_btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        self.cancel_btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            self._cancel()

    def on_text(self, text: str):
        pass
