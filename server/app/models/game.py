from __future__ import annotations

from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")

    white_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    black_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    winner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    white_elo_before: Mapped[int] = mapped_column(Integer, nullable=False)
    black_elo_before: Mapped[int] = mapped_column(Integer, nullable=False)
    white_elo_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_elo_after: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
