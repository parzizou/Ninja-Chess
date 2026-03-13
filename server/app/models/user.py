from __future__ import annotations

from datetime import datetime
from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Elo ratings
    elo_standard: Mapped[int] = mapped_column(Integer, default=1000)
    elo_rumble: Mapped[int] = mapped_column(Integer, default=1000)

    # Stats
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_won: Mapped[int] = mapped_column(Integer, default=0)
    games_lost: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
