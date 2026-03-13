from __future__ import annotations

import arcade
from utils.constants import COLOR_INPUT_BG, COLOR_TEXT, COLOR_PRIMARY


class TextInput:
    """A simple text input field."""

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        placeholder: str = "",
        is_password: bool = False,
        font_size: int = 14,
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.placeholder = placeholder
        self.is_password = is_password
        self.font_size = font_size
        self.text = ""
        self.focused = False
        self._cursor_timer = 0.0
        self._show_cursor = True

    def draw(self):
        # Background
        border_color = COLOR_PRIMARY if self.focused else (80, 80, 90)
        arcade.draw_rectangle_filled(self.x, self.y, self.width, self.height, COLOR_INPUT_BG)
        arcade.draw_rectangle_outline(self.x, self.y, self.width, self.height, border_color, 2)

        # Text
        display = self.text
        if self.is_password and display:
            display = "*" * len(display)

        if display:
            arcade.draw_text(
                display,
                self.x - self.width / 2 + 10,
                self.y,
                COLOR_TEXT,
                font_size=self.font_size,
                anchor_x="left",
                anchor_y="center",
            )
        elif not self.focused:
            arcade.draw_text(
                self.placeholder,
                self.x - self.width / 2 + 10,
                self.y,
                (120, 120, 130),
                font_size=self.font_size,
                anchor_x="left",
                anchor_y="center",
            )

        # Cursor
        if self.focused and self._show_cursor:
            text_width = len(display) * (self.font_size * 0.6)
            cx = self.x - self.width / 2 + 10 + text_width
            cx = min(cx, self.x + self.width / 2 - 5)
            arcade.draw_line(cx, self.y - 10, cx, self.y + 10, COLOR_TEXT, 2)

    def update(self, dt: float):
        self._cursor_timer += dt
        if self._cursor_timer >= 0.5:
            self._cursor_timer = 0.0
            self._show_cursor = not self._show_cursor

    def check_click(self, mx: float, my: float) -> bool:
        hit = (
            self.x - self.width / 2 <= mx <= self.x + self.width / 2
            and self.y - self.height / 2 <= my <= self.y + self.height / 2
        )
        self.focused = hit
        if hit:
            self._show_cursor = True
            self._cursor_timer = 0.0
        return hit

    def on_key_press(self, key: int, modifiers: int):
        if not self.focused:
            return
        if key == arcade.key.BACKSPACE:
            self.text = self.text[:-1]
        elif key == arcade.key.V and (modifiers & arcade.key.MOD_CTRL):
            pass  # clipboard paste not trivially supported

    def on_text(self, text: str):
        if not self.focused:
            return
        # Filter to printable characters
        for ch in text:
            if ch.isprintable() and ch not in ("\r", "\n"):
                self.text += ch
