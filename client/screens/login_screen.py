from __future__ import annotations

import arcade
import threading

from components.button import Button
from components.text_input import TextInput
from utils.constants import (
    WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG, COLOR_TEXT, COLOR_PRIMARY, COLOR_DANGER,
)
from utils.api import api
from utils.credentials import save_credentials


class LoginScreen:
    """Login / Register screen."""

    def __init__(self, window: arcade.Window):
        self.window = window
        self.username_input = TextInput(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 60, 300, 40,
            placeholder="Nom d'utilisateur",
        )
        self.password_input = TextInput(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2, 300, 40,
            placeholder="Mot de passe",
            is_password=True,
        )
        self.login_btn = Button(
            WINDOW_WIDTH / 2 - 80, WINDOW_HEIGHT / 2 - 70, 140, 40,
            "Connexion", on_click=self._do_login,
        )
        self.register_btn = Button(
            WINDOW_WIDTH / 2 + 80, WINDOW_HEIGHT / 2 - 70, 140, 40,
            "Créer un compte", on_click=self._do_register,
            font_size=12,
        )

        self.stay_connected = True
        self.stay_btn = Button(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 120, 250, 30,
            "☑ Rester connecté", on_click=self._toggle_stay,
            color=(60, 60, 70),
            hover_color=(80, 80, 90),
            font_size=12,
        )
        self.offline_ai_btn = Button(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 240, 250, 38,
            "Jouer vs IA (sans compte)",
            on_click=lambda: self.window.show_screen("ai_difficulty"),
            color=(55, 90, 60), hover_color=(70, 115, 75), font_size=13,
        )

        self.error_message = ""
        self.loading = False
        self.inputs = [self.username_input, self.password_input]
        self.buttons = [self.login_btn, self.register_btn, self.stay_btn, self.offline_ai_btn]

    def _toggle_stay(self):
        self.stay_connected = not self.stay_connected
        label = "☑ Rester connecté" if self.stay_connected else "☐ Rester connecté"
        self.stay_btn.text = label

    def _do_login(self):
        self._auth_action("login")

    def _do_register(self):
        self._auth_action("register")

    def _auth_action(self, action: str):
        username = self.username_input.text.strip()
        password = self.password_input.text.strip()

        if not username or not password:
            self.error_message = "Veuillez remplir tous les champs"
            return

        self.loading = True
        self.error_message = ""

        def _call():
            try:
                if action == "login":
                    data = api.login(username, password)
                else:
                    data = api.register(username, password)

                token = data["access_token"]
                api.set_token(token)

                if self.stay_connected:
                    save_credentials(username, token)

                # Store user info on window for other screens
                self.window.user_data = {
                    "username": data["username"],
                    "token": token,
                    "elo_standard": data["elo_standard"],
                    "elo_rumble": data["elo_rumble"],
                }
                self.loading = False
                self.window.show_screen("home")

            except Exception as e:
                self.loading = False
                err = str(e)
                if "409" in err:
                    self.error_message = "Ce nom d'utilisateur est déjà pris"
                elif "401" in err:
                    self.error_message = "Identifiants incorrects"
                else:
                    self.error_message = f"Erreur de connexion au serveur"

        threading.Thread(target=_call, daemon=True).start()

    def on_draw(self):
        arcade.draw_rectangle_filled(
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2,
            WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_BG,
        )

        # Title
        arcade.draw_text(
            "NINJA CHESS",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 180,
            COLOR_TEXT, font_size=36,
            anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            "Échecs en temps réel",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 + 140,
            (180, 180, 180), font_size=14,
            anchor_x="center", anchor_y="center",
        )

        # Labels
        arcade.draw_text(
            "Utilisateur", WINDOW_WIDTH / 2 - 150, WINDOW_HEIGHT / 2 + 85,
            (180, 180, 180), font_size=11,
        )
        arcade.draw_text(
            "Mot de passe", WINDOW_WIDTH / 2 - 150, WINDOW_HEIGHT / 2 + 25,
            (180, 180, 180), font_size=11,
        )

        for inp in self.inputs:
            inp.draw()
        for btn in self.buttons:
            btn.draw()

        arcade.draw_text(
            "── ou ──",
            WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 205,
            (90, 90, 100), font_size=11,
            anchor_x="center", anchor_y="center",
        )

        if self.error_message:
            arcade.draw_text(
                self.error_message,
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 160,
                COLOR_DANGER, font_size=12,
                anchor_x="center", anchor_y="center",
            )

        if self.loading:
            arcade.draw_text(
                "Connexion en cours...",
                WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2 - 190,
                (180, 180, 180), font_size=12,
                anchor_x="center", anchor_y="center",
            )

    def on_update(self, dt: float):
        for inp in self.inputs:
            inp.update(dt)

    def on_mouse_motion(self, x, y, dx, dy):
        for btn in self.buttons:
            btn.check_hover(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        for inp in self.inputs:
            inp.check_click(x, y)
        for btn in self.buttons:
            btn.check_click(x, y)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.TAB:
            # Cycle focus between inputs
            if self.username_input.focused:
                self.username_input.focused = False
                self.password_input.focused = True
            else:
                self.username_input.focused = True
                self.password_input.focused = False
        elif key == arcade.key.ENTER:
            self._do_login()
        else:
            for inp in self.inputs:
                inp.on_key_press(key, modifiers)

    def on_text(self, text: str):
        for inp in self.inputs:
            inp.on_text(text)
