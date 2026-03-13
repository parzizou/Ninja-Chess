from __future__ import annotations

import socketio
import threading
from typing import Callable, Any

SERVER_URL = "https://ninja-chess.parzizou.fr"


class SocketClient:
    """Manages the Socket.IO connection to the server.

    Runs the socketio client in a background thread so that
    the arcade main loop is not blocked.
    """

    def __init__(self, server_url: str = SERVER_URL):
        self.server_url = server_url
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=5)
        self._thread: threading.Thread | None = None
        self._connected = False

        # Register internal handlers
        self.sio.on("connect", self._on_connect)
        self.sio.on("disconnect", self._on_disconnect)

    def _on_connect(self):
        self._connected = True
        print("[SOCKET] Connected to server")

    def _on_disconnect(self):
        self._connected = False
        print("[SOCKET] Disconnected from server")

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, token: str):
        """Connect to the server with JWT authentication."""
        def _run():
            try:
                self.sio.connect(
                    self.server_url,
                    auth={"token": token},
                    transports=["websocket", "polling"],
                )
                self.sio.wait()
            except Exception as e:
                print(f"[SOCKET] Connection error: {e}")

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def disconnect(self):
        """Disconnect from the server."""
        if self._connected:
            self.sio.disconnect()

    def on(self, event: str, handler: Callable):
        """Register an event handler."""
        self.sio.on(event, handler)

    def emit(self, event: str, data: Any = None):
        """Emit an event to the server."""
        if self._connected:
            self.sio.emit(event, data)


# Singleton
socket_client = SocketClient()
