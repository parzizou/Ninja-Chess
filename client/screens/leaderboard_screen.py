from __future__ import annotations

import threading

import arcade

from components.button import Button
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT, COLOR_PANEL_BG,
)
from utils.api import api


class LeaderboardScreen:
    """Displays the top players by Elo ranking."""

    def __init__(self, window: arcade.Window):
        self.window = window
        self.entries: list[dict] = []
        self.loading = True
        self.error = ""

        self.back_btn = Button(
            80, WINDOW_HEIGHT - 30, 100, 30,
            "← Retour", on_click=lambda: self.window.show_screen("home"),
            color=(60, 60, 70), font_size=12,
        )

    def on_show(self):
        self.loading = True
        self.error = ""

        def _fetch():
            try:
                self.entries = api.get_leaderboard()
                self.loading = False
            except Exception:
                self.error = "Impossible de charger le classement"
                self.loading = False

        threading.Thread(target=_fetch, daemon=True).start()

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )

        arcade.draw_text(
            "Classement",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 40,
            COLOR_TEXT, font_size=26,
            anchor_x="center", anchor_y="center", bold=True,
        )

        self.back_btn.draw()

        if self.loading:
            arcade.draw_text(
                "Chargement...",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
                (150, 150, 150), font_size=16,
                anchor_x="center", anchor_y="center",
            )
            return

        if self.error:
            arcade.draw_text(
                self.error,
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
                (200, 80, 80), font_size=14,
                anchor_x="center", anchor_y="center",
            )
            return

        # Header
        y = WINDOW_HEIGHT - 90
        arcade.draw_text("#", 80, y, (180, 180, 180), font_size=12, bold=True)
        arcade.draw_text("Joueur", 130, y, (180, 180, 180), font_size=12, bold=True)
        arcade.draw_text("Elo", 450, y, (180, 180, 180), font_size=12, bold=True)
        arcade.draw_text("Parties", 570, y, (180, 180, 180), font_size=12, bold=True)
        arcade.draw_text("Victoires", 700, y, (180, 180, 180), font_size=12, bold=True)

        # Rows
        for i, entry in enumerate(self.entries[:20]):
            y = WINDOW_HEIGHT - 120 - i * 28
            if y < 60:
                break

            # Alternating row background
            if i % 2 == 0:
                arcade.draw_rectangle_filled(
                    WINDOW_WIDTH / 2, y + 5,
                    WINDOW_WIDTH - 60, 26,
                    (40, 40, 50, 150),
                )

            color = COLOR_TEXT
            if entry["rank"] == 1:
                color = (255, 215, 0)
            elif entry["rank"] == 2:
                color = (192, 192, 192)
            elif entry["rank"] == 3:
                color = (205, 127, 50)

            arcade.draw_text(str(entry["rank"]), 80, y, color, font_size=12, bold=True)
            arcade.draw_text(entry["username"], 130, y, color, font_size=12)
            arcade.draw_text(str(entry["elo_standard"]), 450, y, color, font_size=12)
            arcade.draw_text(str(entry["games_played"]), 570, y, color, font_size=12)
            arcade.draw_text(str(entry["games_won"]), 700, y, color, font_size=12)

    def on_update(self, dt: float):
        pass

    def on_mouse_motion(self, x, y, dx, dy):
        self.back_btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        self.back_btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            self.window.show_screen("home")

    def on_text(self, text: str):
        pass
