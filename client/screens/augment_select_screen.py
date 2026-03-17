from __future__ import annotations

import math
import time
import arcade

from components.button import Button
from utils.constants import WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT
from utils.socket_client import socket_client


# Augment card colors by type
CARD_COLOR = (55, 45, 65)
CARD_HOVER = (75, 60, 90)
CARD_SELECTED = (50, 130, 80)
GOLD_COLORS = [(180, 150, 50), (210, 175, 60), (240, 200, 80), (255, 220, 100)]


class AugmentSelectScreen:
    """Augment selection phase between Rumble rounds."""

    def __init__(self, window: arcade.Window):
        self.window = window
        self.proposals: list[dict] = []
        self.round_num: int = 1
        self.scores: dict = {"white": 0, "black": 0}
        self.my_augments: list[dict] = []
        self.opp_augments: list[dict] = []
        self.selected_index: int | None = None
        self.confirmed: bool = False
        self.waiting_opponent: bool = False
        self.skipped: bool = False

        self.reroll_btns: list[Button] = []
        self.select_btns: list[Button] = []
        self.back_btn = Button(
            80, WINDOW_HEIGHT - 25, 100, 30, "← Quitter",
            on_click=self._leave, color=(80, 40, 40), font_size=12,
        )

        self._register_socket_events()

    def _register_socket_events(self):
        socket_client.on("rumble:augment_phase", self._on_augment_phase)
        socket_client.on("rumble:rerolled", self._on_rerolled)
        socket_client.on("rumble:augment_confirmed", self._on_confirmed)
        socket_client.on("rumble:opponent_selected", self._on_opponent_selected)
        socket_client.on("rumble:round_start", self._on_round_start)

    def on_show(self):
        data = getattr(self.window, "rumble_augment_data", None)
        if data:
            self._setup(data)

    def _setup(self, data: dict):
        self.round_num = data.get("round", 1)
        self.proposals = data.get("proposals", [])
        self.scores = data.get("scores", {"white": 0, "black": 0})
        self.my_augments = data.get("my_augments", [])
        self.opp_augments = data.get("opponent_augments", [])
        self.skipped = data.get("skipped", False)
        self.selected_index = None
        self.confirmed = False
        self.waiting_opponent = False

        if self.skipped:
            self.confirmed = True
            self.waiting_opponent = True
            return

        self._build_buttons()

    def _build_buttons(self):
        self.reroll_btns.clear()
        self.select_btns.clear()

        card_w = 220
        total_w = len(self.proposals) * card_w + (len(self.proposals) - 1) * 20
        start_x = (WINDOW_WIDTH - total_w) / 2 + card_w / 2

        for i in range(len(self.proposals)):
            x = start_x + i * (card_w + 20)

            reroll = Button(
                x, 160, 100, 30, "Relancer",
                on_click=lambda idx=i: self._reroll(idx),
                color=(120, 80, 40), hover_color=(150, 100, 50), font_size=11,
            )
            self.reroll_btns.append(reroll)

            select = Button(
                x, 120, 100, 30, "Choisir",
                on_click=lambda idx=i: self._select(idx),
                color=(40, 100, 60), hover_color=(50, 130, 75), font_size=11,
            )
            self.select_btns.append(select)

    def _reroll(self, index: int):
        if self.confirmed:
            return
        socket_client.emit("rumble:reroll", {"index": index})

    def _select(self, index: int):
        if self.confirmed or index >= len(self.proposals):
            return
        aug = self.proposals[index]
        self.selected_index = index
        self.confirmed = True
        self.waiting_opponent = True
        socket_client.emit("rumble:select_augment", {"augment_id": aug["id"]})

    def _leave(self):
        socket_client.emit("rumble:leave_room")
        self.window.show_screen("home")

    def _on_augment_phase(self, data):
        self.window.rumble_augment_data = data
        self._setup(data)

    def _on_rerolled(self, data):
        index = data.get("index", -1)
        aug = data.get("augment")
        if 0 <= index < len(self.proposals) and aug:
            self.proposals[index] = aug
            if index < len(self.reroll_btns):
                self.reroll_btns[index].enabled = False
                self.reroll_btns[index].text = "Utilisé"

    def _on_confirmed(self, data):
        pass

    def _on_opponent_selected(self, data):
        pass

    def _on_round_start(self, data):
        self.window.rumble_round_data = data
        self.window.show_screen("rumble_game")

    # ── Drawing ──────────────────────────────────────────────

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )

        # Title
        arcade.draw_text(
            f"RUMBLE — Manche {self.round_num}",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 30,
            (255, 180, 80), font_size=22, anchor_x="center", anchor_y="center", bold=True,
        )

        # Score diamond
        self._draw_score_diamond(WINDOW_WIDTH / 2, WINDOW_HEIGHT - 70)

        self.back_btn.draw()

        if self.skipped:
            arcade.draw_text(
                "L'adversaire a utilisé Aura Farming — pas d'augment ce tour",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
                (200, 100, 100), font_size=16, anchor_x="center", anchor_y="center",
            )
            arcade.draw_text(
                "En attente de l'adversaire...",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 40,
                (180, 180, 180), font_size=14, anchor_x="center", anchor_y="center",
            )
            return

        # Augment cards
        arcade.draw_text(
            "Choisissez un augment :", WINDOW_WIDTH / 2, WINDOW_HEIGHT - 110,
            (200, 200, 210), font_size=16, anchor_x="center", anchor_y="center",
        )

        card_w = 220
        card_h = 280
        total_w = len(self.proposals) * card_w + (len(self.proposals) - 1) * 20
        start_x = (WINDOW_WIDTH - total_w) / 2 + card_w / 2

        for i, aug in enumerate(self.proposals):
            x = start_x + i * (card_w + 20)
            y = WINDOW_HEIGHT / 2 + 30

            is_selected = self.selected_index == i
            color = CARD_SELECTED if is_selected else CARD_COLOR
            arcade.draw_rectangle_filled(x, y, card_w, card_h, color)

            border_color = (255, 220, 100) if is_selected else (100, 80, 120)
            arcade.draw_rectangle_outline(x, y, card_w, card_h, border_color, 2)

            # Name
            arcade.draw_text(
                aug.get("name", "???"), x, y + card_h / 2 - 25,
                (255, 220, 100), font_size=13, anchor_x="center", anchor_y="center", bold=True,
                width=int(card_w - 20), align="center",
            )

            # Description (wrapped)
            desc = aug.get("description", "")
            arcade.draw_text(
                desc, x - card_w / 2 + 12, y + card_h / 2 - 50,
                (200, 200, 210), font_size=10, width=int(card_w - 24),
                multiline=True, anchor_y="top",
            )

            # Activable badge
            if aug.get("is_activable"):
                badge_y = y - card_h / 2 + 55
                arcade.draw_text(
                    f"Activable ({aug.get('cooldown', 0):.0f}s)",
                    x, badge_y, (255, 150, 50), font_size=10,
                    anchor_x="center", anchor_y="center", bold=True,
                )

        # Buttons
        if not self.confirmed:
            for btn in self.reroll_btns + self.select_btns:
                btn.draw()

        if self.waiting_opponent:
            arcade.draw_text(
                "En attente de l'adversaire...",
                WINDOW_WIDTH / 2, 70,
                (180, 180, 180), font_size=14, anchor_x="center", anchor_y="center",
            )

        # Active augments sidebar
        self._draw_augment_sidebar(30, "Vos augments", self.my_augments, left=True)
        self._draw_augment_sidebar(WINDOW_WIDTH - 30, "Adversaire", self.opp_augments, left=False)

    def _draw_score_diamond(self, cx: float, cy: float):
        """Draw the BO7 score diamond (4 squares)."""
        size = 14
        gap = 2
        # 2x2 diamond layout rotated 45 degrees → just draw 4 squares in a row for simplicity
        for player_color, offset_y in [("white", -size - gap), ("black", size + gap)]:
            score = self.scores.get(player_color, 0)
            for i in range(4):
                sx = cx - (1.5 * (size + gap)) + i * (size + gap)
                sy = cy + offset_y
                if i < score:
                    gidx = min(i, len(GOLD_COLORS) - 1)
                    fill = GOLD_COLORS[gidx]
                else:
                    fill = (60, 60, 70)
                arcade.draw_rectangle_filled(sx, sy, size, size, fill)
                arcade.draw_rectangle_outline(sx, sy, size, size, (120, 120, 130), 1)

        arcade.draw_text("Vous", cx - 60, cy, (180, 180, 190), font_size=9,
                         anchor_x="right", anchor_y="center")
        arcade.draw_text("Adv.", cx + 60, cy, (180, 180, 190), font_size=9,
                         anchor_x="left", anchor_y="center")

    def _draw_augment_sidebar(self, x: float, title: str, augments: list[dict], left: bool):
        arcade.draw_text(
            title, x, WINDOW_HEIGHT - 130,
            (160, 160, 170), font_size=10, anchor_x="left" if left else "right",
            anchor_y="center", bold=True,
        )
        for i, aug in enumerate(augments):
            y = WINDOW_HEIGHT - 155 - i * 20
            name = aug.get("name", "?")
            color = (180, 160, 100) if aug.get("is_activable") else (150, 150, 160)
            arcade.draw_text(
                f"• {name}", x, y, color, font_size=9,
                anchor_x="left" if left else "right", anchor_y="center",
            )

    def on_update(self, dt: float):
        pass

    def on_mouse_motion(self, x, y, dx, dy):
        self.back_btn.check_hover(x, y)
        for btn in self.reroll_btns + self.select_btns:
            btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        if self.back_btn.check_click(x, y):
            return
        if not self.confirmed:
            for btn in self.reroll_btns:
                if btn.check_click(x, y):
                    return
            for btn in self.select_btns:
                if btn.check_click(x, y):
                    return

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            self._leave()

    def on_text(self, text: str):
        pass
