from __future__ import annotations

import os
import sys

# ── Window ──────────────────────────────────────────────
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700
WINDOW_TITLE = "Ninja Chess"

# ── Board ───────────────────────────────────────────────
BOARD_SIZE = 8
SQUARE_SIZE = 80
BOARD_PIXEL = BOARD_SIZE * SQUARE_SIZE  # 640
BOARD_OFFSET_X = (WINDOW_WIDTH - BOARD_PIXEL) // 2  # center horizontally
BOARD_OFFSET_Y = (WINDOW_HEIGHT - BOARD_PIXEL) // 2  # center vertically

# ── Colors ──────────────────────────────────────────────
COLOR_LIGHT_SQUARE = (240, 217, 181)
COLOR_DARK_SQUARE = (181, 136, 99)
COLOR_HIGHLIGHT = (255, 255, 0, 80)
COLOR_BG = (30, 30, 30)
COLOR_PRIMARY = (45, 120, 200)
COLOR_PRIMARY_HOVER = (60, 140, 220)
COLOR_DANGER = (200, 50, 50)
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_DARK = (20, 20, 20)
COLOR_INPUT_BG = (50, 50, 60)
COLOR_PANEL_BG = (40, 40, 50, 220)

# ── Server ──────────────────────────────────────────────
SERVER_URL = "https://ninja-chess.parzizou.fr"
API_URL = f"{SERVER_URL}"

# ── Assets ──────────────────────────────────────────────
def _get_base_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


ASSETS_DIR = os.path.join(_get_base_dir(), "assets")
SPRITES_DIR = os.path.join(ASSETS_DIR, "sprites")

# ── Cooldowns (client mirror for visual feedback) ──────
COOLDOWNS = {
    "pawn": 1.0,
    "knight": 3.0,
    "bishop": 3.0,
    "rook": 4.0,
    "queen": 5.0,
    "king": 3.0,
}
