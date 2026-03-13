from __future__ import annotations

import threading

import arcade

from components.button import Button
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT, COLOR_PRIMARY,
)
from utils.api import api


class ProfileScreen:
    """Player profile with stats and match history."""

    def __init__(self, window: arcade.Window):
        self.window = window
        self.profile: dict | None = None
        self.history: list[dict] = []
        self.loading = True
        self.error = ""

        self.back_btn = Button(
            80, WINDOW_HEIGHT - 30, 100, 30,
            "← Retour", on_click=lambda: self.window.show_screen("home"),
            color=(60, 60, 70), font_size=12,
        )
        self.avatar_btn = Button(
            WINDOW_WIDTH / 2, 40, 200, 36,
            "Changer l'avatar", on_click=self._pick_avatar,
            font_size=12,
        )

    def on_show(self):
        self.loading = True
        self.error = ""
        user = getattr(self.window, "user_data", None)
        if not user:
            self.window.show_screen("login")
            return

        username = user["username"]

        def _fetch():
            try:
                self.profile = api.get_profile(username)
                self.history = api.get_history(username)
                self.loading = False
            except Exception:
                self.error = "Impossible de charger le profil"
                self.loading = False

        threading.Thread(target=_fetch, daemon=True).start()

    def _pick_avatar(self):
        # In a real app, would open a file dialog.
        # For now, this is a placeholder.
        pass

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )

        arcade.draw_text(
            "Mon Profil",
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

        if not self.profile:
            return

        p = self.profile
        cx = WINDOW_WIDTH / 2
        y = WINDOW_HEIGHT - 100

        # Stats
        stats = [
            ("Joueur", p["username"]),
            ("Elo Standard", str(p["elo_standard"])),
            ("Elo Rumble", str(p["elo_rumble"])),
            ("Parties jouées", str(p["games_played"])),
            ("Victoires", str(p["games_won"])),
            ("Défaites", str(p["games_lost"])),
        ]

        for label, value in stats:
            arcade.draw_text(label, cx - 120, y, (150, 150, 160), font_size=13)
            arcade.draw_text(value, cx + 80, y, COLOR_TEXT, font_size=13, bold=True)
            y -= 30

        # History
        y -= 20
        arcade.draw_text(
            "Dernières parties", cx, y,
            COLOR_TEXT, font_size=16,
            anchor_x="center", anchor_y="center", bold=True,
        )
        y -= 30

        for game in self.history[:10]:
            if y < 80:
                break
            result_color = (100, 255, 100) if game["result"] == "win" else (255, 100, 100)
            result_label = "V" if game["result"] == "win" else "D"
            elo_str = f"+{game['elo_change']}" if game["elo_change"] >= 0 else str(game["elo_change"])

            arcade.draw_text(result_label, cx - 200, y, result_color, font_size=12, bold=True)
            arcade.draw_text(f"vs {game['opponent']}", cx - 160, y, COLOR_TEXT, font_size=12)
            arcade.draw_text(elo_str, cx + 100, y, result_color, font_size=12)
            arcade.draw_text(game["mode"], cx + 170, y, (120, 120, 130), font_size=11)
            y -= 25

        self.avatar_btn.draw()

    def on_update(self, dt: float):
        pass

    def on_mouse_motion(self, x, y, dx, dy):
        self.back_btn.check_hover(x, y)
        self.avatar_btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        self.back_btn.check_click(x, y)
        self.avatar_btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            self.window.show_screen("home")

    def on_text(self, text: str):
        pass
