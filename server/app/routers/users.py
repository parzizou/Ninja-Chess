from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.game import Game
from app.schemas.user import UserProfile, LeaderboardEntry
from app.schemas.game import GameHistory
from app.routers.auth import get_user_from_token

router = APIRouter(tags=["users"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")


def _get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    """Extract Bearer token from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization[7:]
    return get_user_from_token(token, db)


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(db: Session = Depends(get_db)):
    users = db.query(User).order_by(desc(User.elo_standard)).limit(100).all()
    return [
        LeaderboardEntry(
            rank=i + 1,
            username=u.username,
            elo_standard=u.elo_standard,
            games_played=u.games_played,
            games_won=u.games_won,
        )
        for i, u in enumerate(users)
    ]


@router.get("/users/{username}/profile", response_model=UserProfile)
def get_profile(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    avatar_url = f"/uploads/{os.path.basename(user.avatar_path)}" if user.avatar_path else None
    return UserProfile(
        username=user.username,
        elo_standard=user.elo_standard,
        elo_rumble=user.elo_rumble,
        games_played=user.games_played,
        games_won=user.games_won,
        games_lost=user.games_lost,
        avatar_url=avatar_url,
    )


@router.get("/users/{username}/history", response_model=list[GameHistory])
def get_history(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    games = (
        db.query(Game)
        .filter((Game.white_id == user.id) | (Game.black_id == user.id))
        .order_by(desc(Game.ended_at))
        .limit(20)
        .all()
    )

    history = []
    for g in games:
        if g.white_id == user.id:
            opponent_id = g.black_id
            elo_before = g.white_elo_before
            elo_after = g.white_elo_after or g.white_elo_before
        else:
            opponent_id = g.white_id
            elo_before = g.black_elo_before
            elo_after = g.black_elo_after or g.black_elo_before

        opponent = db.query(User).filter(User.id == opponent_id).first()
        opponent_name = opponent.username if opponent else "Unknown"

        history.append(GameHistory(
            id=g.id,
            mode=g.mode,
            opponent=opponent_name,
            result="win" if g.winner_id == user.id else "loss",
            elo_change=elo_after - elo_before,
            played_at=g.ended_at or g.started_at,
        ))

    return history


@router.post("/users/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(status_code=400, detail="Only PNG, JPEG or WebP allowed")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    filename = f"{user.id}_{uuid.uuid4().hex[:8]}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 2 MB)")

    with open(path, "wb") as f:
        f.write(content)

    # Remove old avatar
    if user.avatar_path and os.path.exists(user.avatar_path):
        os.remove(user.avatar_path)

    user.avatar_path = path
    db.commit()

    return {"avatar_url": f"/uploads/{filename}"}
