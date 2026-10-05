from __future__ import annotations

import os
from contextlib import asynccontextmanager

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.database import init_db
from app.routers import auth, users
from app.events.game_handler import register_events
from app.events.rumble_handler import register_rumble_events

# ── Helpers ──────────────────────────────────────────────

_origins_raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
CORS_ORIGINS: list[str] | str = "*" if _origins_raw == "*" else [o.strip() for o in _origins_raw.split(",")]

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

# ── Socket.IO ────────────────────────────────────────────

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=CORS_ORIGINS,
)

register_events(sio)
register_rumble_events(sio)

# ── FastAPI ──────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()
    print("[SERVER] Database initialized")
    print("[SERVER] Ninja Chess server is running")
    yield


app = FastAPI(title="Ninja Chess", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if isinstance(CORS_ORIGINS, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Uploaded avatars share the origin of the game: never let a browser sniff them as HTML."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.include_router(auth.router)
app.include_router(users.router)

# Serve uploaded avatars
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# The browser client (single page app). Mounted last so the API routes above win.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# ── Combined ASGI app ───────────────────────────────────

combined_app = socketio.ASGIApp(sio, app)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:combined_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8200")),
        reload=True,
    )
