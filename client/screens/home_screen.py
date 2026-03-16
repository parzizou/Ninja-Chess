from __future__ import annotations

import arcade

from components.button import Button
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT, COLOR_PRIMARY, COLOR_DANGER,
)
from utils.credentials import clear_credentials
from utils.api import api
from utils.socket_client import socket_client


class HomeScreen:
    """Main menu after login."""

    def __init__(self, window: arcade.Window):
        self.window = window

        cx = WINDOW_WIDTH / 2
        cy = WINDOW_HEIGHT / 2

        self.buttons = [
            Button(cx, cy + 110, 280, 50, "Jouer - Standard",
                   on_click=lambda: self._play_standard(), font_size=16),
            Button(cx, cy + 50, 280, 50, "Jouer vs IA",
                   on_click=lambda: self.window.show_screen("ai_difficulty"), font_size=16),
            Button(cx, cy - 10, 280, 50, "Jouer - Rumble (bientôt)",
                   on_click=None, color=(80, 80, 90), font_size=14),
            Button(cx, cy - 70, 280, 50, "Classement",
                   on_click=lambda: self.window.show_screen("leaderboard"), font_size=16),
            Button(cx, cy - 130, 280, 50, "Mon Profil",
                   on_click=lambda: self.window.show_screen("profile"), font_size=16),
            Button(cx, cy - 220, 180, 40, "Déconnexion",
                   on_click=self._logout, color=COLOR_DANGER, font_size=13),
        ]
        # Rumble button disabled
        self.buttons[2].enabled = False

    def _play_standard(self):
        # Connect to socket if not already connected
        user = getattr(self.window, "user_data", None)
        if user and not socket_client.connected:
            socket_client.connect(user["token"])
        self.window.show_screen("rooms")

    def _logout(self):
        clear_credentials()
        api.clear_token()
        socket_client.disconnect()
        self.window.user_data = None
        self.window.show_screen("login")

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )

        user = getattr(self.window, "user_data", None)
        name = user["username"] if user else "Joueur"
        elo = user.get("elo_standard", 1000) if user else 1000

        arcade.draw_text(
            "NINJA CHESS",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 60,
            COLOR_TEXT, font_size=28,
            anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            f"Bienvenue, {name}  |  Elo: {elo}",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 100,
            (180, 180, 180), font_size=14,
            anchor_x="center", anchor_y="center",
        )

        for btn in self.buttons:
            btn.draw()

    def on_update(self, dt: float):
        pass

    def on_mouse_motion(self, x, y, dx, dy):
        for btn in self.buttons:
            btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        for btn in self.buttons:
            btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        pass

    def on_text(self, text: str):
        pass
