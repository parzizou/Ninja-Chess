from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class GameHistory(BaseModel):
    id: int
    mode: str
    opponent: str
    result: str  # "win", "loss"
    elo_change: int
    played_at: datetime

    model_config = {"from_attributes": True}
