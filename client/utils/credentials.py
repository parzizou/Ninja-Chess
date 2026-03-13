from __future__ import annotations

import json
import os
from typing import Any

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "credentials.json")


def save_credentials(username: str, token: str):
    """Save login credentials for 'stay connected' feature."""
    data = {"username": username, "token": token}
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_credentials() -> dict[str, str] | None:
    """Load saved credentials, or None if not found / invalid."""
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "username" in data and "token" in data:
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def clear_credentials():
    """Remove saved credentials."""
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)
