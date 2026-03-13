from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ninja_chess.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite-specific
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (used at startup)."""
    Base.metadata.create_all(bind=engine)
