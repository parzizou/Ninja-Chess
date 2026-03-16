from __future__ import annotations

import arcade

from components.button import Button
from utils.constants import WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT


class AIDifficultyScreen:
    """Difficulty selection screen before a Player vs AI game."""

    _DIFFICULTIES = [
        ("Facile",    "easy",   (60, 160, 80),  (75, 185, 95)),
        ("Moyen",     "medium", (45, 120, 200), (60, 140, 220)),
        ("Difficile", "hard",   (180, 50, 50),  (210, 70, 70)),
    ]

    def __init__(self, window: arcade.Window):
        self.window = window
        cx = WINDOW_WIDTH / 2
        cy = WINDOW_HEIGHT / 2

        self.diff_buttons: list[Button] = []
        for i, (label, diff, color, hover) in enumerate(self._DIFFICULTIES):
            y = cy + 50 - i * 75
            self.diff_buttons.append(Button(
                cx, y, 280, 56, label,
                on_click=lambda d=diff: self._start(d),
                color=color, hover_color=hover, font_size=18,
            ))

        self.back_btn = Button(
            80, WINDOW_HEIGHT - 30, 100, 30, "← Retour",
            on_click=self._go_back,
            color=(80, 40, 40), font_size=12,
        )

    def _go_back(self):
        dest = "home" if getattr(self.window, "user_data", None) else "login"
        self.window.show_screen(dest)

    def _start(self, difficulty: str):
        self.window.game_init_data = {"difficulty": difficulty}
        self.window.show_screen("ai_game")

    # ── Screen interface ────────────────────────────────────

    def on_show(self):
        pass

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )
        arcade.draw_text(
            "Jouer contre l'IA",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 80,
            COLOR_TEXT, font_size=26,
            anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            "Choisissez la difficulté",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 125,
            (170, 170, 180), font_size=14,
            anchor_x="center", anchor_y="center",
        )
        arcade.draw_text(
            "Sans impact sur l'Elo",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 148,
            (130, 130, 140), font_size=11,
            anchor_x="center", anchor_y="center",
        )
        for btn in self.diff_buttons:
            btn.draw()
        self.back_btn.draw()

    def on_update(self, dt: float):
        pass

    def on_mouse_motion(self, x, y, dx, dy):
        for btn in self.diff_buttons:
            btn.check_hover(x, y)
        self.back_btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        for btn in self.diff_buttons:
            btn.check_click(x, y)
        self.back_btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            self.window.show_screen("home")

    def on_text(self, text: str):
        pass
