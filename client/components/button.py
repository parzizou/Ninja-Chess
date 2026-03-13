from __future__ import annotations

import arcade
from utils.constants import COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_TEXT


class Button:
    """A simple clickable button drawn with arcade shapes."""

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        text: str,
        on_click=None,
        color=COLOR_PRIMARY,
        hover_color=COLOR_PRIMARY_HOVER,
        text_color=COLOR_TEXT,
        font_size: int = 14,
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.on_click = on_click
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.font_size = font_size
        self.hovered = False
        self.enabled = True

    def draw(self):
        color = self.hover_color if self.hovered else self.color
        if not self.enabled:
            color = (100, 100, 100)

        arcade.draw_rectangle_filled(self.x, self.y, self.width, self.height, color)
        arcade.draw_rectangle_outline(self.x, self.y, self.width, self.height, (255, 255, 255, 60), 2)
        arcade.draw_text(
            self.text,
            self.x,
            self.y,
            self.text_color,
            font_size=self.font_size,
            anchor_x="center",
            anchor_y="center",
            bold=True,
        )

    def check_hover(self, mx: float, my: float):
        self.hovered = (
            self.x - self.width / 2 <= mx <= self.x + self.width / 2
            and self.y - self.height / 2 <= my <= self.y + self.height / 2
        )

    def check_click(self, mx: float, my: float) -> bool:
        if not self.enabled:
            return False
        if (
            self.x - self.width / 2 <= mx <= self.x + self.width / 2
            and self.y - self.height / 2 <= my <= self.y + self.height / 2
        ):
            if self.on_click:
                self.on_click()
            return True
        return False
