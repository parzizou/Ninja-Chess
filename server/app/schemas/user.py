from __future__ import annotations

from pydantic import BaseModel


class UserProfile(BaseModel):
    username: str
    elo_standard: int
    elo_rumble: int
    games_played: int
    games_won: int
    games_lost: int
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    elo_standard: int
    games_played: int
    games_won: int

    model_config = {"from_attributes": True}
