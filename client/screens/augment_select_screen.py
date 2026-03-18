from __future__ import annotations

import math
import arcade

from components.button import Button
from utils.constants import WINDOW_WIDTH, WINDOW_HEIGHT
from utils.socket_client import socket_client


# ── Visual palette ────────────────────────────────────────────
BG_DEEP        = (15, 10, 25)
CARD_BG        = (32, 22, 48)
CARD_HOVER_C   = (44, 32, 64)
CARD_SEL_BG    = (26, 58, 40)
GOLD_MID       = (210, 168, 50)
GOLD_BRIGHT    = (255, 215, 90)
GOLD_SCORES    = [(148, 108, 22), (188, 148, 38), (222, 178, 52), (255, 210, 78)]
ACCENT_ACT     = (220, 130, 35)   # orange — activable
ACCENT_PASS    = (70, 130, 210)   # blue   — passive
TEXT_BRIGHT    = (238, 228, 250)
TEXT_DIM       = (158, 146, 172)


def _key_name(key: int) -> str:
    """Return a readable display string for an arcade key constant."""
    if 97 <= key <= 122:   # a-z
        return chr(key).upper()
    if 48 <= key <= 57:    # 0-9
        return chr(key)
    special = {
        arcade.key.F1: "F1",   arcade.key.F2: "F2",   arcade.key.F3: "F3",
        arcade.key.F4: "F4",   arcade.key.F5: "F5",   arcade.key.F6: "F6",
        arcade.key.F7: "F7",   arcade.key.F8: "F8",   arcade.key.F9: "F9",
        arcade.key.F10: "F10", arcade.key.F11: "F11", arcade.key.F12: "F12",
        arcade.key.SPACE: "Esp",
        arcade.key.ENTER: "Entr",
        arcade.key.TAB: "Tab",
        arcade.key.UP: "↑", arcade.key.DOWN: "↓",
        arcade.key.LEFT: "←", arcade.key.RIGHT: "→",
    }
    return special.get(key, "?")


class AugmentSelectScreen:
    """Augment selection phase between Rumble rounds."""

    CARD_W    = 232
    CARD_H    = 350
    CARD_GAP  = 28
    CARD_Y    = WINDOW_HEIGHT / 2 + 10
    REROLL_R  = 17

    def __init__(self, window: arcade.Window):
        self.window = window
        self.proposals:   list[dict] = []
        self.round_num:   int        = 1
        self.scores:      dict       = {"white": 0, "black": 0}
        self.my_augments: list[dict] = []
        self.opp_augments: list[dict] = []
        self.selected_index: int | None = None
        self.confirmed:       bool      = False
        self.waiting_opponent: bool     = False
        self.skipped:         bool      = False
        self.reroll_used:     list[bool] = []

        # Keybind capture
        self._keybind_pending:  bool      = False
        self._keybind_pending_idx: int | None = None

        # Hover
        self._hover_card:   int | None = None
        self._hover_reroll: int | None = None

        # Animation timer
        self._t: float = 0.0

        self._back_btn = Button(
            70, WINDOW_HEIGHT - 25, 100, 28, "← Quitter",
            on_click=self._leave, color=(65, 32, 32), font_size=11,
        )
        self._register_socket_events()

    def _register_socket_events(self):
        socket_client.on("rumble:augment_phase",    self._on_augment_phase)
        socket_client.on("rumble:rerolled",          self._on_rerolled)
        socket_client.on("rumble:augment_confirmed", self._on_confirmed)
        socket_client.on("rumble:opponent_selected", self._on_opponent_selected)
        socket_client.on("rumble:round_start",       self._on_round_start)

    def on_show(self):
        data = getattr(self.window, "rumble_augment_data", None)
        if data:
            self._setup(data)

    def _setup(self, data: dict):
        self.round_num      = data.get("round", 1)
        self.proposals      = data.get("proposals", [])
        self.scores         = data.get("scores", {"white": 0, "black": 0})
        self.my_augments    = data.get("my_augments", [])
        self.opp_augments   = data.get("opponent_augments", [])
        self.skipped        = data.get("skipped", False)
        self.selected_index = None
        self.confirmed      = False
        self.waiting_opponent = False
        self._keybind_pending     = False
        self._keybind_pending_idx = None
        self.reroll_used    = [False] * len(self.proposals)

    # ── Card geometry ─────────────────────────────────────────

    def _card_cx(self, i: int) -> float:
        n = len(self.proposals)
        total = n * self.CARD_W + (n - 1) * self.CARD_GAP
        return (WINDOW_WIDTH - total) / 2 + self.CARD_W / 2 + i * (self.CARD_W + self.CARD_GAP)

    def _reroll_pos(self, i: int) -> tuple[float, float]:
        return self._card_cx(i), self.CARD_Y - self.CARD_H / 2 + 26

    def _in_card(self, mx: float, my: float, i: int) -> bool:
        cx = self._card_cx(i)
        cy = self.CARD_Y
        return (cx - self.CARD_W / 2 <= mx <= cx + self.CARD_W / 2
                and cy - self.CARD_H / 2 <= my <= cy + self.CARD_H / 2)

    def _in_reroll(self, mx: float, my: float, i: int) -> bool:
        rx, ry = self._reroll_pos(i)
        return math.hypot(mx - rx, my - ry) <= self.REROLL_R

    # ── Actions ───────────────────────────────────────────────

    def _reroll(self, i: int):
        if self.confirmed or self.reroll_used[i]:
            return
        socket_client.emit("rumble:reroll", {"index": i})

    def _click_card(self, i: int):
        if self.confirmed:
            return
        aug = self.proposals[i]
        if aug.get("is_activable"):
            self._keybind_pending     = True
            self._keybind_pending_idx = i
        else:
            self._confirm_select(i, None)

    def _confirm_select(self, i: int, keybind: int | None):
        aug = self.proposals[i]
        self.selected_index   = i
        self.confirmed        = True
        self.waiting_opponent = True
        if keybind is not None:
            if not hasattr(self.window, "rumble_keybinds"):
                self.window.rumble_keybinds = {}
            self.window.rumble_keybinds[aug["id"]] = keybind
        socket_client.emit("rumble:select_augment", {"augment_id": aug["id"]})

    def _leave(self):
        socket_client.emit("rumble:leave_room")
        self.window.show_screen("home")

    # ── Socket callbacks ──────────────────────────────────────

    def _on_augment_phase(self, data):
        self.window.rumble_augment_data = data
        self._setup(data)

    def _on_rerolled(self, data):
        i   = data.get("index", -1)
        aug = data.get("augment")
        if 0 <= i < len(self.proposals) and aug:
            self.proposals[i] = aug
            if i < len(self.reroll_used):
                self.reroll_used[i] = True

    def _on_confirmed(self, data):
        pass

    def _on_opponent_selected(self, data):
        pass

    def _on_round_start(self, data):
        self.window.rumble_round_data = data
        self.window.show_screen("rumble_game")

    # ── Drawing ───────────────────────────────────────────────

    def on_draw(self):
        self._draw_bg()
        self._draw_header()

        if self.skipped:
            self._draw_skipped_message()
        else:
            for i, aug in enumerate(self.proposals):
                self._draw_card(i, aug)
            if self.waiting_opponent:
                self._draw_waiting_banner()

        self._draw_sidebars()
        self._back_btn.draw()

        if self._keybind_pending:
            self._draw_keybind_overlay()

    def _draw_bg(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, WINDOW_WIDTH, WINDOW_HEIGHT, BG_DEEP,
        )
        # Subtle radial glow in the center
        for radius, alpha in [(420, 15), (290, 20), (185, 14)]:
            arcade.draw_circle_filled(
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 25, radius, (65, 42, 115, alpha),
            )
        # Top/bottom vignette bars
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 28, WINDOW_WIDTH, 56, (22, 14, 36, 130),
        )
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, 28, WINDOW_WIDTH, 56, (18, 10, 30, 130),
        )

    def _draw_header(self):
        # Title shadow
        arcade.draw_text(
            f"RUMBLE  —  Manche {self.round_num}",
            WINDOW_WIDTH / 2 + 2, WINDOW_HEIGHT - 32,
            (35, 18, 4), font_size=24,
            anchor_x="center", anchor_y="center", bold=True,
        )
        # Title
        arcade.draw_text(
            f"RUMBLE  —  Manche {self.round_num}",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 30,
            GOLD_BRIGHT, font_size=24,
            anchor_x="center", anchor_y="center", bold=True,
        )
        # Subtitle
        arcade.draw_text(
            "Choisissez votre augment pour cette manche",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT - 60,
            TEXT_DIM, font_size=12, anchor_x="center", anchor_y="center",
        )
        # Score
        self._draw_score(WINDOW_WIDTH / 2, WINDOW_HEIGHT - 95)

    def _draw_score(self, cx: float, cy: float):
        sq  = 14
        gap = 3
        total_w = 3 * sq + 2 * gap
        for player, oy, label in [("white", sq + 5, "Vous"), ("black", -(sq + 5), "Adv.")]:
            score = self.scores.get(player, 0)
            x0 = cx - total_w / 2 + sq / 2
            for i in range(3):
                sx = x0 + i * (sq + gap)
                sy = cy + oy
                half = sq * 0.55
                pts = [(sx, sy + half), (sx + half, sy), (sx, sy - half), (sx - half, sy)]
                fill = GOLD_SCORES[i] if i < score else (38, 30, 52)
                arcade.draw_polygon_filled(pts, fill)
                for j in range(4):
                    p1, p2 = pts[j], pts[(j + 1) % 4]
                    arcade.draw_line(p1[0], p1[1], p2[0], p2[1], (88, 78, 108), 1)
            arcade.draw_text(
                label, cx - total_w / 2 - 8, cy + oy,
                TEXT_DIM, font_size=9, anchor_x="right", anchor_y="center",
            )

    def _draw_card(self, i: int, aug: dict):
        cx = self._card_cx(i)
        cy = self.CARD_Y
        w, h = self.CARD_W, self.CARD_H
        is_sel = self.selected_index == i
        is_hov = self._hover_card == i and not self.confirmed
        is_act = aug.get("is_activable", False)
        accent = ACCENT_ACT if is_act else ACCENT_PASS

        # Drop shadow
        arcade.draw_rectangle_filled(cx + 5, cy - 5, w + 4, h + 4, (0, 0, 0, 55))

        # Card body
        if is_sel:
            bg = CARD_SEL_BG
        elif is_hov:
            bg = CARD_HOVER_C
        else:
            bg = CARD_BG
        arcade.draw_rectangle_filled(cx, cy, w, h, bg)

        # Border / glow
        if is_sel:
            arcade.draw_rectangle_outline(cx, cy, w + 10, h + 10, (*GOLD_BRIGHT[:3], 18), 3)
            arcade.draw_rectangle_outline(cx, cy, w + 4,  h + 4,  (*GOLD_BRIGHT[:3], 55), 2)
            arcade.draw_rectangle_outline(cx, cy, w,      h,       GOLD_BRIGHT,            2)
        else:
            a = 155 if is_hov else 75
            arcade.draw_rectangle_outline(cx, cy, w, h, (*accent, a), 2)

        # Top color accent strip
        arcade.draw_rectangle_filled(cx, cy + h / 2 - 5, w, 10, accent)

        # Type label
        arcade.draw_text(
            "ACTIVABLE" if is_act else "PASSIF",
            cx, cy + h / 2 - 20,
            accent, font_size=8, anchor_x="center", anchor_y="center", bold=True,
        )

        # Augment name
        arcade.draw_text(
            aug.get("name", "???"),
            cx, cy + h / 2 - 42,
            GOLD_BRIGHT, font_size=12,
            anchor_x="center", anchor_y="center", bold=True,
            width=int(w - 20), align="center",
        )

        # Thin divider
        arcade.draw_line(
            cx - w / 2 + 18, cy + h / 2 - 60,
            cx + w / 2 - 18, cy + h / 2 - 60,
            (*TEXT_DIM, 55), 1,
        )

        # Description
        arcade.draw_text(
            aug.get("description", ""),
            cx - w / 2 + 14, cy + h / 2 - 70,
            TEXT_BRIGHT, font_size=9,
            width=int(w - 28), multiline=True, anchor_y="top",
        )

        # Activable badge near bottom
        if is_act:
            bx, by = cx, cy - h / 2 + 72
            bw, bh = w - 24, 24
            arcade.draw_rectangle_filled(bx, by, bw, bh, (*ACCENT_ACT, 28))
            arcade.draw_rectangle_outline(bx, by, bw, bh, ACCENT_ACT, 1)
            arcade.draw_text(
                f"Cooldown : {aug.get('cooldown', 0):.0f}s",
                bx, by, ACCENT_ACT,
                font_size=9, anchor_x="center", anchor_y="center", bold=True,
            )

        # Hover hint
        if is_hov and not self.confirmed:
            hint = "Clic → assigner une touche" if is_act else "Clic → choisir cet augment"
            hy = cy - h / 2 + (98 if is_act else 72)
            arcade.draw_text(
                hint, cx, hy, TEXT_DIM,
                font_size=8, anchor_x="center", anchor_y="center",
            )

        # Reroll circle button (inside card bottom area, only if not yet selected)
        if not self.confirmed and not is_sel:
            self._draw_reroll_btn(i)

    def _draw_reroll_btn(self, i: int):
        rx, ry = self._reroll_pos(i)
        used = self.reroll_used[i] if i < len(self.reroll_used) else False
        hov  = self._hover_reroll == i

        if used:
            fill      = (52, 44, 62)
            border    = (78, 68, 90)
            icon_col  = (105, 95, 118)
            icon      = "✓"
        elif hov:
            fill      = (138, 88, 28)
            border    = GOLD_BRIGHT
            icon_col  = GOLD_BRIGHT
            icon      = "↺"
        else:
            fill      = (78, 52, 16)
            border    = (148, 108, 38)
            icon_col  = (198, 152, 52)
            icon      = "↺"

        arcade.draw_circle_filled(rx, ry, self.REROLL_R, fill)
        arcade.draw_circle_outline(rx, ry, self.REROLL_R, border, 2)
        arcade.draw_text(
            icon, rx, ry, icon_col,
            font_size=13, anchor_x="center", anchor_y="center", bold=True,
        )

    def _draw_keybind_overlay(self):
        i = self._keybind_pending_idx
        if i is None or i >= len(self.proposals):
            return
        aug = self.proposals[i]

        # Dim entire screen
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, WINDOW_WIDTH, WINDOW_HEIGHT, (0, 0, 0, 165),
        )

        # Modal panel
        pw, ph = 500, 192
        px, py = WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2
        arcade.draw_rectangle_filled(px, py, pw, ph, (22, 14, 36))
        # Outer glow border
        arcade.draw_rectangle_outline(px, py, pw + 10, ph + 10, (*GOLD_MID[:3], 35), 3)
        arcade.draw_rectangle_outline(px, py, pw,      ph,       GOLD_MID,          2)

        arcade.draw_text(
            "Assigner une touche",
            px, py + ph / 2 - 28,
            GOLD_BRIGHT, font_size=18, anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            aug.get("name", ""),
            px, py + ph / 2 - 54,
            TEXT_DIM, font_size=11, anchor_x="center", anchor_y="center",
        )
        arcade.draw_line(
            px - 180, py - 2, px + 180, py - 2, (*TEXT_DIM, 40), 1,
        )

        # Pulsing prompt text
        pulse = 0.5 + 0.5 * math.sin(self._t * 3.0)
        r = int(192 + 62 * pulse)
        g = int(152 + 52 * pulse)
        arcade.draw_text(
            "Appuyez sur une touche...",
            px, py + 18,
            (r, g, 48), font_size=14, anchor_x="center", anchor_y="center",
        )

        arcade.draw_text(
            "Échap pour annuler",
            px, py - ph / 2 + 24,
            TEXT_DIM, font_size=10, anchor_x="center", anchor_y="center",
        )

    def _draw_waiting_banner(self):
        arcade.draw_text(
            "✓  Augment sélectionné — En attente de l'adversaire...",
            WINDOW_WIDTH / 2, 50,
            GOLD_MID, font_size=12, anchor_x="center", anchor_y="center",
        )

    def _draw_skipped_message(self):
        arcade.draw_text(
            "L'adversaire a utilisé Aura Farming",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 25,
            (200, 88, 88), font_size=18, anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            "Vous ne recevez pas d'augment ce tour.",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 18,
            TEXT_DIM, font_size=13, anchor_x="center", anchor_y="center",
        )
        arcade.draw_text(
            "En attente de l'adversaire...",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 52,
            TEXT_DIM, font_size=11, anchor_x="center", anchor_y="center",
        )

    def _draw_sidebars(self):
        self._draw_one_sidebar(28,                  "Vos augments", self.my_augments,  left=True)
        self._draw_one_sidebar(WINDOW_WIDTH - 28,   "Adversaire",   self.opp_augments, left=False)

    def _draw_one_sidebar(self, x: float, title: str, augments: list[dict], left: bool):
        anchor = "left" if left else "right"
        arcade.draw_text(
            title, x, WINDOW_HEIGHT - 115,
            GOLD_MID, font_size=10, anchor_x=anchor, anchor_y="center", bold=True,
        )
        end_x = x + (128 if left else -128)
        arcade.draw_line(x, WINDOW_HEIGHT - 127, end_x, WINDOW_HEIGHT - 127, (*TEXT_DIM, 48), 1)
        for j, aug in enumerate(augments):
            y = WINDOW_HEIGHT - 145 - j * 20
            if y < 20:
                break
            col = ACCENT_ACT if aug.get("is_activable") else TEXT_DIM
            arcade.draw_text(
                f"• {aug.get('name', '?')}",
                x, y, col, font_size=9, anchor_x=anchor, anchor_y="center",
            )

    # ── Event handlers ────────────────────────────────────────

    def on_update(self, dt: float):
        self._t += dt

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        self._back_btn.check_hover(x, y)
        if self.confirmed or self._keybind_pending:
            self._hover_card   = None
            self._hover_reroll = None
            return
        self._hover_card   = None
        self._hover_reroll = None
        for i in range(len(self.proposals)):
            if self._in_reroll(x, y, i):
                self._hover_reroll = i
                break
            if self._in_card(x, y, i):
                self._hover_card = i
                break

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        if self._back_btn.check_click(x, y):
            return
        if self._keybind_pending or self.confirmed:
            return
        # Reroll buttons are inside card bounds — check them first
        for i in range(len(self.proposals)):
            if self._in_reroll(x, y, i) and not self.reroll_used[i]:
                self._reroll(i)
                return
        # Card body click → select
        for i in range(len(self.proposals)):
            if self._in_card(x, y, i):
                self._click_card(i)
                return

    def on_key_press(self, key: int, modifiers: int):
        if key == arcade.key.ESCAPE:
            if self._keybind_pending:
                self._keybind_pending     = False
                self._keybind_pending_idx = None
            else:
                self._leave()
            return

        if self._keybind_pending and self._keybind_pending_idx is not None:
            # Ignore bare modifier keys
            if key in (
                arcade.key.LSHIFT, arcade.key.RSHIFT,
                arcade.key.LCTRL,  arcade.key.RCTRL,
                arcade.key.LALT,   arcade.key.RALT,
                arcade.key.LMETA,  arcade.key.RMETA,
            ):
                return
            idx = self._keybind_pending_idx
            self._keybind_pending     = False
            self._keybind_pending_idx = None
            self._confirm_select(idx, key)

    def on_text(self, text: str):
        pass
