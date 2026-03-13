from __future__ import annotations

import os

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import auth, users
from app.events.game_handler import register_events

# ── Socket.IO ────────────────────────────────────────────

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
)

register_events(sio)

# ── FastAPI ──────────────────────────────────────────────

app = FastAPI(title="Ninja Chess", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)

# Serve uploaded avatars
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ── Combined ASGI app ───────────────────────────────────

combined_app = socketio.ASGIApp(sio, other_app=app)


@app.on_event("startup")
def on_startup():
    init_db()
    print("[SERVER] Database initialized")
    print("[SERVER] Ninja Chess server is running")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:combined_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8200")),
        reload=True,
    )
