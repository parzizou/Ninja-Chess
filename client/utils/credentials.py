from __future__ import annotations

import json
import os
from pathlib import Path


def _get_credentials_file() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        base_dir = Path(appdata) / "NinjaChess"
    else:
        base_dir = Path.home() / ".ninja_chess"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "credentials.json"


CREDENTIALS_FILE = _get_credentials_file()
LEGACY_CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / "credentials.json"


def _migrate_legacy_credentials() -> None:
    if CREDENTIALS_FILE.exists() or not LEGACY_CREDENTIALS_FILE.exists():
        return
    try:
        CREDENTIALS_FILE.write_text(
            LEGACY_CREDENTIALS_FILE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    except OSError:
        pass


def save_credentials(username: str, token: str):
    """Save login credentials for 'stay connected' feature."""
    data = {"username": username, "token": token}
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_credentials() -> dict[str, str] | None:
    """Load saved credentials, or None if not found / invalid."""
    _migrate_legacy_credentials()
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
