from __future__ import annotations

"""Socket.IO event handlers for room and game management."""

import time
from datetime import datetime, timezone

import socketio
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.events.rooms import room_manager, GameState
from app.logic.board import Color
from app.logic.moves import is_valid_move
from app.logic.elo import compute_new_ratings
from app.models.user import User
from app.models.game import Game
from app.routers.auth import decode_token


def get_user_from_sid(sio: socketio.AsyncServer, sid: str) -> dict | None:
    """Retrieve stored user info from the session."""
    session = sio.get_session(sid)
    return session if session else None


async def get_user_from_sid_async(sio: socketio.AsyncServer, sid: str) -> dict | None:
    session = await sio.get_session(sid)
    return session if session else None


def register_events(sio: socketio.AsyncServer):
    """Register all Socket.IO event handlers."""

    @sio.event
    async def connect(sid, environ, auth):
        """Authenticate the socket connection via JWT."""
        token = None
        if auth and isinstance(auth, dict):
            token = auth.get("token")

        if not token:
            raise socketio.exceptions.ConnectionRefusedError("No token provided")

        payload = decode_token(token)
        if payload is None:
            raise socketio.exceptions.ConnectionRefusedError("Invalid token")

        username = payload.get("sub")
        if not username:
            raise socketio.exceptions.ConnectionRefusedError("Invalid token")

        # Look up user in DB
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise socketio.exceptions.ConnectionRefusedError("User not found")
            user_id = user.id
        finally:
            db.close()

        await sio.save_session(sid, {
            "username": username,
            "user_id": user_id,
        })
        print(f"[WS] {username} connected (sid={sid})")

    @sio.event
    async def disconnect(sid):
        session = await sio.get_session(sid)
        username = session.get("username", "?") if session else "?"

        # Check if player is in a game — if so, opponent wins by disconnect
        game = room_manager.get_game_by_sid(sid)
        if game and not game.finished:
            await _handle_disconnect_forfeit(sio, sid, game)

        room_manager.leave_room(sid)
        print(f"[WS] {username} disconnected (sid={sid})")

    # ── Room events ──────────────────────────────────────────

    @sio.on("room:create")
    async def on_room_create(sid, data):
        session = await sio.get_session(sid)
        if not session:
            return

        name = data.get("name", f"{session['username']}'s room")
        room = room_manager.create_room(name, sid, session["username"], session["user_id"])
        await sio.enter_room(sid, room.room_id)

        # Notify the creator
        await sio.emit("room:created", room.to_dict(), to=sid)
        # Broadcast updated room list
        await sio.emit("room:list", room_manager.available_rooms())

    @sio.on("room:join")
    async def on_room_join(sid, data):
        session = await sio.get_session(sid)
        if not session:
            return

        room_id = data.get("room_id")
        room = room_manager.join_room(room_id, sid, session["username"], session["user_id"])
        if room is None:
            await sio.emit("room:error", {"message": "Room not found or full"}, to=sid)
            return

        await sio.enter_room(sid, room.room_id)
        # Broadcast updated room list (room is now full)
        await sio.emit("room:list", room_manager.available_rooms())

        # Start the game
        game = room_manager.start_game(room_id)
        if game:
            state = game.board.to_state()
            await sio.emit("room:ready", {
                "room_id": room_id,
                "white": game.white_username,
                "black": game.black_username,
                "state": state,
                "your_color": "white",
            }, to=game.white_sid)
            await sio.emit("room:ready", {
                "room_id": room_id,
                "white": game.white_username,
                "black": game.black_username,
                "state": state,
                "your_color": "black",
            }, to=game.black_sid)

    @sio.on("room:leave")
    async def on_room_leave(sid, data=None):
        room_id = room_manager.leave_room(sid)
        if room_id:
            await sio.leave_room(sid, room_id)
            await sio.emit("room:list", room_manager.available_rooms())

    @sio.on("room:refresh")
    async def on_room_refresh(sid, data=None):
        await sio.emit("room:list", room_manager.available_rooms(), to=sid)

    # ── Game events ──────────────────────────────────────────

    @sio.on("game:move")
    async def on_game_move(sid, data):
        game = room_manager.get_game_by_sid(sid)
        if game is None or game.finished:
            await sio.emit("game:move_ack", {"ok": False, "reason": "No active game"}, to=sid)
            return

        # Determine player color
        if sid == game.white_sid:
            player_color = Color.WHITE
            opponent_sid = game.black_sid
        elif sid == game.black_sid:
            player_color = Color.BLACK
            opponent_sid = game.white_sid
        else:
            return

        from_row = data.get("from_row")
        from_col = data.get("from_col")
        to_row = data.get("to_row")
        to_col = data.get("to_col")

        if any(v is None for v in (from_row, from_col, to_row, to_col)):
            await sio.emit("game:move_ack", {"ok": False, "reason": "Missing fields"}, to=sid)
            return

        piece = game.board.piece_at(from_row, from_col)

        if piece is None or piece.color != player_color:
            await sio.emit("game:move_ack", {"ok": False, "reason": "No piece or not yours"}, to=sid)
            return

        now = time.time()
        if piece.is_on_cooldown(now):
            await sio.emit("game:move_ack", {
                "ok": False,
                "reason": "Piece on cooldown",
                "cooldown_remaining": round(piece.remaining_cooldown(now), 2),
            }, to=sid)
            return

        if not is_valid_move(game.board, piece, to_row, to_col):
            await sio.emit("game:move_ack", {"ok": False, "reason": "Invalid move"}, to=sid)
            return

        # Execute move
        captured = game.board.piece_at(to_row, to_col)
        if captured:
            captured.alive = False

        piece.row = to_row
        piece.col = to_col
        piece.last_move_time = now

        # ACK to mover
        await sio.emit("game:move_ack", {
            "ok": True,
            "from_row": from_row,
            "from_col": from_col,
            "to_row": to_row,
            "to_col": to_col,
            "cooldown": piece.cooldown_duration,
            "captured": captured.to_dict(now) if captured else None,
        }, to=sid)

        # Notify opponent
        await sio.emit("game:opponent_move", {
            "from_row": from_row,
            "from_col": from_col,
            "to_row": to_row,
            "to_col": to_col,
            "piece_type": piece.piece_type.value,
            "piece_color": piece.color.value,
            "cooldown": piece.cooldown_duration,
            "captured": captured.to_dict(now) if captured else None,
        }, to=opponent_sid)

        # Check for king capture
        if captured and captured.piece_type.value == "king":
            game.finished = True
            game.winner_color = player_color
            await _finish_game(sio, game)


async def _handle_disconnect_forfeit(sio: socketio.AsyncServer, disconnected_sid: str, game: GameState):
    """Handle a player disconnecting mid-game."""
    game.finished = True
    if disconnected_sid == game.white_sid:
        game.winner_color = Color.BLACK
        winner_sid = game.black_sid
    else:
        game.winner_color = Color.WHITE
        winner_sid = game.white_sid

    await sio.emit("game:over", {
        "winner": game.winner_color.value,
        "reason": "opponent_disconnected",
    }, to=winner_sid)

    await _record_game_result(game)
    room_manager.remove_game(game.room_id)


async def _finish_game(sio: socketio.AsyncServer, game: GameState):
    """Announce game over and record the result."""
    await sio.emit("game:over", {
        "winner": game.winner_color.value,
        "reason": "king_captured",
    }, room=game.room_id)

    await _record_game_result(game)
    room_manager.remove_game(game.room_id)


async def _record_game_result(game: GameState):
    """Persist game result to DB and update elo."""
    db: Session = SessionLocal()
    try:
        white = db.query(User).filter(User.id == game.white_user_id).first()
        black = db.query(User).filter(User.id == game.black_user_id).first()
        if not white or not black:
            return

        winner_id = game.white_user_id if game.winner_color == Color.WHITE else game.black_user_id

        if game.winner_color == Color.WHITE:
            new_w, new_b = compute_new_ratings(white.elo_standard, black.elo_standard)
        else:
            new_b, new_w = compute_new_ratings(black.elo_standard, white.elo_standard)

        record = Game(
            mode="standard",
            white_id=white.id,
            black_id=black.id,
            winner_id=winner_id,
            white_elo_before=white.elo_standard,
            black_elo_before=black.elo_standard,
            white_elo_after=new_w,
            black_elo_after=new_b,
            ended_at=datetime.now(timezone.utc),
        )
        db.add(record)

        white.elo_standard = new_w
        black.elo_standard = new_b
        white.games_played += 1
        black.games_played += 1
        if winner_id == white.id:
            white.games_won += 1
            black.games_lost += 1
        else:
            black.games_won += 1
            white.games_lost += 1

        db.commit()
    finally:
        db.close()
