from __future__ import annotations

import requests
from typing import Any

from utils.constants import API_URL


class ApiClient:
    """HTTP client for REST endpoints (auth, leaderboard, profile)."""

    def __init__(self):
        self.token: str | None = None
        self.session = requests.Session()

    def set_token(self, token: str):
        self.token = token
        self.session.headers["Authorization"] = f"Bearer {token}"

    def clear_token(self):
        self.token = None
        self.session.headers.pop("Authorization", None)

    def register(self, username: str, password: str) -> dict[str, Any]:
        resp = self.session.post(f"{API_URL}/auth/register", json={
            "username": username,
            "password": password,
        })
        resp.raise_for_status()
        return resp.json()

    def login(self, username: str, password: str) -> dict[str, Any]:
        resp = self.session.post(f"{API_URL}/auth/login", json={
            "username": username,
            "password": password,
        })
        resp.raise_for_status()
        return resp.json()

    def get_leaderboard(self) -> list[dict[str, Any]]:
        resp = self.session.get(f"{API_URL}/leaderboard")
        resp.raise_for_status()
        return resp.json()

    def get_profile(self, username: str) -> dict[str, Any]:
        resp = self.session.get(f"{API_URL}/users/{username}/profile")
        resp.raise_for_status()
        return resp.json()

    def get_history(self, username: str) -> list[dict[str, Any]]:
        resp = self.session.get(f"{API_URL}/users/{username}/history")
        resp.raise_for_status()
        return resp.json()

    def upload_avatar(self, file_path: str) -> dict[str, Any]:
        with open(file_path, "rb") as f:
            resp = self.session.post(
                f"{API_URL}/users/avatar",
                files={"file": f},
            )
        resp.raise_for_status()
        return resp.json()


# Singleton
api = ApiClient()
