from __future__ import annotations

import arcade

# ── Arcade 3.0 compatibility shims ─────────────────────
# Arcade 3.0 removed several draw_* functions. Restore them
# so that all screens keep using the 2.x-style API unchanged.

if not hasattr(arcade, "draw_rectangle_filled"):
    def _draw_rectangle_filled(cx, cy, w, h, color, tilt_angle=0):
        arcade.draw_rect_filled(arcade.XYWH(cx, cy, w, h), color, tilt_angle)
    arcade.draw_rectangle_filled = _draw_rectangle_filled

if not hasattr(arcade, "draw_rectangle_outline"):
    def _draw_rectangle_outline(cx, cy, w, h, color, border_width=1, tilt_angle=0):
        arcade.draw_rect_outline(arcade.XYWH(cx, cy, w, h), color, border_width, tilt_angle)
    arcade.draw_rectangle_outline = _draw_rectangle_outline

if not hasattr(arcade, "set_background_color"):
    def _set_background_color(color):
        pass  # Handled via window.background_color in __init__
    arcade.set_background_color = _set_background_color

# ────────────────────────────────────────────────────────

from utils.constants import WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_TITLE
from utils.credentials import load_credentials
from utils.api import api
from utils.socket_client import socket_client

from screens.login_screen import LoginScreen
from screens.home_screen import HomeScreen
from screens.room_screen import RoomScreen
from screens.waiting_screen import WaitingScreen
from screens.game_screen import GameScreen
from screens.ai_difficulty_screen import AIDifficultyScreen
from screens.ai_game_screen import AIGameScreen
from screens.leaderboard_screen import LeaderboardScreen
from screens.profile_screen import ProfileScreen


class NinjaChessWindow(arcade.Window):
    """Main application window with screen management."""

    def __init__(self):
        super().__init__(WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_TITLE, resizable=False)
        self.background_color = (30, 30, 30)

        self.user_data: dict | None = None
        self.game_init_data: dict | None = None

        # Create screens
        self.screens: dict[str, object] = {
            "login": LoginScreen(self),
            "home": HomeScreen(self),
            "rooms": RoomScreen(self),
            "waiting": WaitingScreen(self),
            "game": GameScreen(self),
            "ai_difficulty": AIDifficultyScreen(self),
            "ai_game": AIGameScreen(self),
            "leaderboard": LeaderboardScreen(self),
            "profile": ProfileScreen(self),
        }
        self.current_screen_name = "login"
        self.current_screen = self.screens["login"]

        # Try auto-login
        self._try_auto_login()

    def _try_auto_login(self):
        """Attempt to log in with saved credentials."""
        creds = load_credentials()
        if creds:
            token = creds["token"]
            username = creds["username"]
            try:
                # Validate token by fetching profile
                api.set_token(token)
                profile = api.get_profile(username)
                self.user_data = {
                    "username": username,
                    "token": token,
                    "elo_standard": profile.get("elo_standard", 1000),
                    "elo_rumble": profile.get("elo_rumble", 1000),
                }
                self.show_screen("home")
            except Exception:
                # Token expired or invalid — stay on login screen
                api.clear_token()

    def show_screen(self, name: str):
        """Switch to a different screen."""
        if name in self.screens:
            self.current_screen_name = name
            self.current_screen = self.screens[name]
            if hasattr(self.current_screen, "on_show"):
                self.current_screen.on_show()

    def on_draw(self):
        self.clear()
        self.current_screen.on_draw()

    def on_update(self, delta_time: float):
        self.current_screen.on_update(delta_time)

    def on_mouse_motion(self, x, y, dx, dy):
        self.current_screen.on_mouse_motion(x, y, dx, dy)

    def on_mouse_press(self, x, y, button, modifiers):
        self.current_screen.on_mouse_press(x, y, button, modifiers)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        handler = getattr(self.current_screen, "on_mouse_drag", None)
        if handler:
            handler(x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x, y, button, modifiers):
        handler = getattr(self.current_screen, "on_mouse_release", None)
        if handler:
            handler(x, y, button, modifiers)

    def on_key_press(self, key, modifiers):
        self.current_screen.on_key_press(key, modifiers)

    def on_text(self, text: str):
        self.current_screen.on_text(text)

    def on_close(self):
        """Clean up on window close."""
        socket_client.disconnect()
        super().on_close()


def main():
    window = NinjaChessWindow()
    arcade.run()


if __name__ == "__main__":
    main()
