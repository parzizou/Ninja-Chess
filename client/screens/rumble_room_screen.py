from __future__ import annotations

import arcade

from components.button import Button
from components.text_input import TextInput
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT, COLOR_PRIMARY,
)
from utils.socket_client import socket_client


class RumbleRoomScreen:
    """Room browser for Rumble mode."""

    def __init__(self, window: arcade.Window):
        self.window = window
        self.rooms: list[dict] = []

        cx = WINDOW_WIDTH / 2

        self.room_name_input = TextInput(
            cx, WINDOW_HEIGHT - 80, 250, 36, placeholder="Nom de la room",
        )
        self.create_btn = Button(
            cx + 165, WINDOW_HEIGHT - 80, 120, 36,
            "Créer", on_click=self._create_room, font_size=13,
        )
        self.back_btn = Button(
            80, WINDOW_HEIGHT - 30, 100, 30,
            "← Retour", on_click=lambda: self.window.show_screen("home"),
            color=(60, 60, 70), font_size=12,
        )
        self.refresh_btn = Button(
            cx, 40, 140, 36,
            "Rafraîchir", on_click=self._refresh, font_size=13,
        )

        self.room_buttons: list[Button] = []
        self.all_buttons = [self.create_btn, self.back_btn, self.refresh_btn]
        self.inputs = [self.room_name_input]

        self._register_socket_events()

    def _register_socket_events(self):
        socket_client.on("rumble:room_list", self._on_room_list)
        socket_client.on("rumble:room_created", self._on_room_created)
        socket_client.on("rumble:augment_phase", self._on_augment_phase)
        socket_client.on("rumble:error", self._on_error)

    def on_show(self):
        self._refresh()

    def _refresh(self):
        socket_client.emit("rumble:refresh_rooms")

    def _create_room(self):
        name = self.room_name_input.text.strip()
        if not name:
            user = getattr(self.window, "user_data", None)
            uname = user["username"] if user else "Joueur"
            name = f"Rumble de {uname}"
        socket_client.emit("rumble:create_room", {"name": name})

    def _on_room_list(self, data):
        self.rooms = data if isinstance(data, list) else []
        self._rebuild_room_buttons()

    def _on_room_created(self, data):
        waiting = self.window.screens.get("waiting")
        if waiting:
            waiting.set_room(data, mode="rumble")
        self.window.show_screen("waiting")

    def _on_augment_phase(self, data):
        # Opponent joined — augment selection starts
        self.window.rumble_augment_data = data
        self.window.show_screen("augment_select")

    def _on_error(self, data):
        pass

    def _rebuild_room_buttons(self):
        self.room_buttons.clear()
        cx = WINDOW_WIDTH / 2
        start_y = WINDOW_HEIGHT - 160
        for i, room in enumerate(self.rooms):
            y = start_y - i * 55
            if y < 80:
                break
            btn = Button(
                cx, y, 500, 45,
                f"{room['name']}  ({room['players']}/2)",
                on_click=lambda rid=room["room_id"]: self._join_room(rid),
                color=(80, 40, 60), hover_color=(100, 55, 80), font_size=13,
            )
            self.room_buttons.append(btn)

    def _join_room(self, room_id: str):
        socket_client.emit("rumble:join_room", {"room_id": room_id})

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )
        arcade.draw_text(
            "RUMBLE — Rooms", WINDOW_WIDTH / 2, WINDOW_HEIGHT - 30,
            (255, 180, 80), font_size=22, anchor_x="center", anchor_y="center", bold=True,
        )
        for inp in self.inputs:
            inp.draw()
        for btn in self.all_buttons:
            btn.draw()
        for btn in self.room_buttons:
            btn.draw()
        if not self.rooms:
            arcade.draw_text(
                "Aucune room Rumble — créez-en une !",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
                (120, 120, 130), font_size=14, anchor_x="center", anchor_y="center",
            )

    def on_update(self, dt: float):
        for inp in self.inputs:
            inp.update(dt)

    def on_mouse_motion(self, x, y, dx, dy):
        for btn in self.all_buttons + self.room_buttons:
            btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        for inp in self.inputs:
            inp.check_click(x, y)
        for btn in self.all_buttons:
            btn.check_click(x, y)
        for btn in self.room_buttons:
            btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ENTER:
            self._create_room()
        else:
            for inp in self.inputs:
                inp.on_key_press(key, modifiers)

    def on_text(self, text: str):
        for inp in self.inputs:
            inp.on_text(text)
