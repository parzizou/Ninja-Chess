from __future__ import annotations

"""Room management via Socket.IO events.

Rooms track waiting players and launch games when two players are matched.
"""

from dataclasses import dataclass, field
from typing import Any

import socketio

from app.logic.board import Board, Color


@dataclass
class Room:
    room_id: str
    name: str
    creator_sid: str
    creator_username: str
    creator_user_id: int
    guest_sid: str | None = None
    guest_username: str | None = None
    guest_user_id: int | None = None

    @property
    def is_full(self) -> bool:
        return self.guest_sid is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "creator": self.creator_username,
            "players": 2 if self.is_full else 1,
        }


@dataclass
class GameState:
    """Holds all state for one active game."""
    room_id: str
    board: Board
    white_sid: str
    black_sid: str
    white_user_id: int
    black_user_id: int
    white_username: str
    black_username: str
    finished: bool = False
    winner_color: Color | None = None


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.games: dict[str, GameState] = {}
        self.sid_to_room: dict[str, str] = {}  # sid -> room_id
        self._next_id = 1

    def create_room(self, name: str, sid: str, username: str, user_id: int) -> Room:
        room_id = f"room_{self._next_id}"
        self._next_id += 1
        room = Room(
            room_id=room_id,
            name=name,
            creator_sid=sid,
            creator_username=username,
            creator_user_id=user_id,
        )
        self.rooms[room_id] = room
        self.sid_to_room[sid] = room_id
        return room

    def join_room(self, room_id: str, sid: str, username: str, user_id: int) -> Room | None:
        room = self.rooms.get(room_id)
        if room is None or room.is_full:
            return None
        room.guest_sid = sid
        room.guest_username = username
        room.guest_user_id = user_id
        self.sid_to_room[sid] = room_id
        return room

    def leave_room(self, sid: str) -> str | None:
        room_id = self.sid_to_room.pop(sid, None)
        if room_id is None:
            return None

        room = self.rooms.get(room_id)
        if room is None:
            return room_id

        if room.creator_sid == sid:
            # Creator left — destroy room
            if room.guest_sid:
                self.sid_to_room.pop(room.guest_sid, None)
            del self.rooms[room_id]
        elif room.guest_sid == sid:
            room.guest_sid = None
            room.guest_username = None
            room.guest_user_id = None

        return room_id

    def start_game(self, room_id: str) -> GameState | None:
        room = self.rooms.get(room_id)
        if room is None or not room.is_full:
            return None

        game = GameState(
            room_id=room_id,
            board=Board(),
            white_sid=room.creator_sid,
            black_sid=room.guest_sid,
            white_user_id=room.creator_user_id,
            black_user_id=room.guest_user_id,
            white_username=room.creator_username,
            black_username=room.guest_username,
        )
        self.games[room_id] = game
        return game

    def get_game_by_sid(self, sid: str) -> GameState | None:
        room_id = self.sid_to_room.get(sid)
        if room_id is None:
            return None
        return self.games.get(room_id)

    def remove_game(self, room_id: str):
        self.games.pop(room_id, None)
        room = self.rooms.pop(room_id, None)
        if room:
            self.sid_to_room.pop(room.creator_sid, None)
            if room.guest_sid:
                self.sid_to_room.pop(room.guest_sid, None)

    def available_rooms(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.rooms.values() if not r.is_full]


# Singleton
room_manager = RoomManager()
