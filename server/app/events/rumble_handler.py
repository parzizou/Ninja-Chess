from __future__ import annotations

"""Socket.IO event handlers for Rumble mode."""

import time
from datetime import datetime, timezone

import socketio
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.events.rooms import room_manager
from app.logic.board import Color, PieceType, COOLDOWNS
from app.logic.moves import is_valid_move, is_in_check
from app.logic.elo import compute_new_ratings
from app.logic.rumble import RumbleMatch, ROUNDS_TO_WIN
from app.models.user import User
from app.models.game import Game
from app.routers.auth import decode_token


def register_rumble_events(sio: socketio.AsyncServer):
    """Register all Socket.IO event handlers for Rumble mode."""

    # ── Room events ──────────────────────────────────────────

    @sio.on("rumble:create_room")
    async def on_rumble_create(sid, data):
        session = await sio.get_session(sid)
        if not session:
            return
        name = data.get("name", f"{session['username']}'s rumble")
        room = room_manager.create_room(name, sid, session["username"], session["user_id"])
        room.mode = "rumble"
        await sio.enter_room(sid, room.room_id)
        await sio.emit("rumble:room_created", room.to_dict(), to=sid)
        await sio.emit("rumble:room_list", room_manager.available_rumble_rooms())

    @sio.on("rumble:join_room")
    async def on_rumble_join(sid, data):
        session = await sio.get_session(sid)
        if not session:
            return
        room_id = data.get("room_id")
        existing = room_manager.rooms.get(room_id)
        if existing and existing.creator_sid == sid:
            await sio.emit("rumble:error", {"message": "Vous ne pouvez pas rejoindre votre propre room"}, to=sid)
            return
        room = room_manager.join_room(room_id, sid, session["username"], session["user_id"])
        if room is None:
            await sio.emit("rumble:error", {"message": "Room introuvable ou déjà pleine"}, to=sid)
            return
        await sio.enter_room(sid, room.room_id)
        await sio.emit("rumble:room_list", room_manager.available_rumble_rooms())

        # Start match
        match = room_manager.start_rumble_match(room_id)
        if match:
            match.generate_proposals()
            await _emit_augment_proposals(sio, match)

    @sio.on("rumble:leave_room")
    async def on_rumble_leave(sid, data=None):
        match = room_manager.get_rumble_match_by_sid(sid)
        if match and not match.finished:
            await _handle_rumble_forfeit(sio, sid, match)
        room_id = room_manager.leave_room(sid)
        if room_id:
            await sio.leave_room(sid, room_id)
            await sio.emit("rumble:room_list", room_manager.available_rumble_rooms())

    @sio.on("rumble:refresh_rooms")
    async def on_rumble_refresh(sid, data=None):
        await sio.emit("rumble:room_list", room_manager.available_rumble_rooms(), to=sid)

    # ── Augment Selection ────────────────────────────────────

    @sio.on("rumble:reroll")
    async def on_rumble_reroll(sid, data):
        match = room_manager.get_rumble_match_by_sid(sid)
        if not match or match.phase != "augment_select":
            return
        color = match.sid_color(sid)
        if not color:
            return
        index = data.get("index", -1)
        new_aug = match.reroll_augment(color, index)
        if new_aug:
            await sio.emit("rumble:rerolled", {
                "index": index,
                "augment": new_aug.to_dict(),
                "infinite": match.aura_farming_winner == color,
            }, to=sid)

    @sio.on("rumble:select_augment")
    async def on_rumble_select(sid, data):
        match = room_manager.get_rumble_match_by_sid(sid)
        if not match or match.phase != "augment_select":
            return
        color = match.sid_color(sid)
        if not color:
            return
        augment_id = data.get("augment_id")
        if not match.select_augment(color, augment_id):
            await sio.emit("rumble:error", {"message": "Sélection invalide"}, to=sid)
            return
        await sio.emit("rumble:augment_confirmed", {"augment_id": augment_id}, to=sid)
        # Notify opponent
        opp_sid = match.opponent_sid(sid)
        await sio.emit("rumble:opponent_selected", {"augment_id": augment_id}, to=opp_sid)

        if match.both_selected():
            match.apply_selections()
            effects = match.start_round()
            await _emit_round_start(sio, match, effects)

    # ── Game Move ────────────────────────────────────────────

    @sio.on("rumble:move")
    async def on_rumble_move(sid, data):
        match = room_manager.get_rumble_match_by_sid(sid)
        if not match or match.phase != "playing" or match.round_finished:
            await sio.emit("rumble:move_ack", {"ok": False, "reason": "Pas de partie active"}, to=sid)
            return

        color = match.sid_color(sid)
        if not color:
            return
        opp_sid = match.opponent_sid(sid)
        opp_color = match.opponent_color(color)

        from_row = data.get("from_row")
        from_col = data.get("from_col")
        to_row = data.get("to_row")
        to_col = data.get("to_col")

        if any(v is None for v in (from_row, from_col, to_row, to_col)):
            await sio.emit("rumble:move_ack", {"ok": False, "reason": "Champs manquants"}, to=sid)
            return

        piece = match.board.piece_at(from_row, from_col)
        if not piece or piece.color.value != color:
            await sio.emit("rumble:move_ack", {"ok": False, "reason": "Pas votre pièce"}, to=sid)
            return

        now = time.time()

        # Check stun
        stun_until = piece.tags.get("stun_until", 0)
        if now < stun_until:
            await sio.emit("rumble:move_ack", {"ok": False, "reason": "Pièce stun"}, to=sid)
            return

        # Check wall
        if piece.tags.get("is_wall"):
            await sio.emit("rumble:move_ack", {"ok": False, "reason": "Pièce immobile"}, to=sid)
            return

        # Check cooldown with augment-modified CD
        cd = match.compute_cooldown(piece)
        if piece.last_move_time > 0 and (now - piece.last_move_time) < cd:
            remaining = cd - (now - piece.last_move_time)
            await sio.emit("rumble:move_ack", {
                "ok": False, "reason": "Cooldown",
                "cooldown_remaining": round(remaining, 2),
            }, to=sid)
            return

        # Validate move (augment-aware)
        valid_moves = match.get_valid_moves(piece)
        if (to_row, to_col) not in valid_moves:
            await sio.emit("rumble:move_ack", {"ok": False, "reason": "Mouvement invalide"}, to=sid)
            return

        # ── Execute move ────────────────────────────────────────
        from_sq = (from_row, from_col)
        to_sq = (to_row, to_col)

        # Check capture
        captured = match.board.piece_at(to_row, to_col)
        ep_captured = None

        # En passant detection
        is_ep = (
            piece.piece_type.value == "pawn"
            and from_col != to_col
            and captured is None
            and match.board.en_passant_square == (to_row, to_col)
            and match.board.en_passant_expires > now
        )
        if is_ep and match.board.en_passant_pawn_pos:
            ep_pawn = match.board.piece_at(*match.board.en_passant_pawn_pos)
            if ep_pawn:
                # Check can_capture
                if match.can_capture(ep_pawn, piece):
                    ep_pawn.alive = False
                    captured = ep_pawn
                    ep_captured = ep_pawn.to_dict(now)

        # Normal capture
        if captured and not is_ep:
            if match.can_capture(captured, piece):
                captured.alive = False
            else:
                captured = None  # invulnerable — no capture

        # Castling
        castling_rook_data = None
        is_castling = (
            piece.piece_type.value == "king"
            and abs(to_col - from_col) == 2
            and from_row == to_row
        )
        if is_castling:
            rook_from_col = 7 if to_col > from_col else 0
            rook_to_col = 5 if to_col > from_col else 3
            rook = match.board.piece_at(from_row, rook_from_col)
            if rook:
                rook.col = rook_to_col
                rook.last_move_time = now
                castling_rook_data = {"row": from_row, "from_col": rook_from_col, "to_col": rook_to_col}

        # Apply move
        piece.row = to_row
        piece.col = to_col
        piece.last_move_time = now

        # En passant state
        if piece.piece_type.value == "pawn" and abs(to_row - from_row) == 2:
            ep_row = (from_row + to_row) // 2
            match.board.en_passant_square = (ep_row, to_col)
            match.board.en_passant_pawn_pos = (to_row, to_col)
            match.board.en_passant_expires = now + 3.0
        else:
            match.board.en_passant_square = None
            match.board.en_passant_pawn_pos = None
            match.board.en_passant_expires = 0.0

        # Promotion
        promoted = False
        promo_row = 7 if piece.color.value == "white" else 0
        if piece.piece_type.value == "pawn" and piece.row == promo_row:
            # Check pouvoir_au_peuple: allow promotion to king
            has_pouvoir = any(a.id == "pouvoir_au_peuple" for a in match.augments[color])
            promo_choice = data.get("promotion", "queen")
            if has_pouvoir and promo_choice == "king":
                piece.piece_type = PieceType.KING
            else:
                piece.piece_type = PieceType.QUEEN
            promoted = True

        # Check detection
        king_in_check = is_in_check(match.board, Color(opp_color))
        if king_in_check:
            opp_king = match.board.king(Color(opp_color))
            if opp_king:
                opp_king.last_move_time = 0.0

        # ── Augment post-move hooks ────────────────────────────
        augment_effects = []

        if captured:
            augment_effects.extend(match.process_capture_effects(captured, piece))

        augment_effects.extend(match.process_move_effects(piece, from_sq, to_sq, captured))

        # Tick effects (meteor, barrier expiry, etc.)
        augment_effects.extend(match.process_tick())

        # Build response data
        effective_cd = match.compute_cooldown(piece)
        ep_sq = list(match.board.en_passant_square) if match.board.en_passant_square else None
        cap_dict = ep_captured or (captured.to_dict(now) if captured else None)

        promoted_to = piece.piece_type.value if promoted else None

        await sio.emit("rumble:move_ack", {
            "ok": True,
            "from_row": from_row, "from_col": from_col,
            "to_row": to_row, "to_col": to_col,
            "cooldown": effective_cd,
            "captured": cap_dict,
            "castling_rook": castling_rook_data,
            "promoted": promoted,
            "promoted_to": promoted_to,
            "opponent_king_in_check": king_in_check,
            "en_passant_square": ep_sq,
            "effects": augment_effects,
        }, to=sid)

        await sio.emit("rumble:opponent_move", {
            "from_row": from_row, "from_col": from_col,
            "to_row": to_row, "to_col": to_col,
            "piece_type": piece.piece_type.value,
            "piece_color": piece.color.value,
            "cooldown": effective_cd,
            "captured": cap_dict,
            "castling_rook": castling_rook_data,
            "promoted": promoted,
            "promoted_to": promoted_to,
            "my_king_in_check": king_in_check,
            "en_passant_square": ep_sq,
            "effects": augment_effects,
        }, to=opp_sid)

        # ── Check round end ────────────────────────────────────
        round_over = False
        winner = None

        # King capture
        if captured and match.check_king_capture(captured):
            round_over = True
            winner = color

        # Extra win conditions
        if not round_over:
            extra = match.check_extra_wins()
            if extra:
                round_over = True
                winner = extra

        # Check if augment effects killed a king
        if not round_over:
            for fx in augment_effects:
                if fx.get("type") == "capture" and fx.get("piece_type") == "king":
                    killed_color = fx.get("color")
                    if killed_color:
                        remaining = match.board.kings(Color(killed_color))
                        multi = match.tags.get(f"multi_king_{killed_color}", False)
                        if not multi or len(remaining) == 0:
                            round_over = True
                            winner = match.opponent_color(killed_color)

        if round_over and winner:
            match_over = match.end_round(winner)
            await _emit_round_over(sio, match, winner, match_over)

    # ── Augment Activation ───────────────────────────────────

    @sio.on("rumble:activate")
    async def on_rumble_activate(sid, data):
        match = room_manager.get_rumble_match_by_sid(sid)
        if not match or match.phase != "playing" or match.round_finished:
            return
        color = match.sid_color(sid)
        if not color:
            return

        augment_id = data.get("augment_id")
        target_row = data.get("target_row")
        target_col = data.get("target_col")

        can, reason = match.can_activate(color, augment_id)
        if not can:
            await sio.emit("rumble:activate_ack", {"ok": False, "reason": reason}, to=sid)
            return

        result = match.activate_augment(color, augment_id, target_row, target_col)

        if not result.get("ok"):
            await sio.emit("rumble:activate_ack", result, to=sid)
            return

        # Tick effects after activation
        tick_effects = match.process_tick()
        all_effects = result.get("effects", []) + tick_effects

        await sio.emit("rumble:activate_ack", {
            "ok": True, "augment_id": augment_id, "effects": all_effects,
        }, to=sid)

        opp_sid = match.opponent_sid(sid)
        await sio.emit("rumble:augment_activated", {
            "augment_id": augment_id, "color": color, "effects": all_effects,
        }, to=opp_sid)

        # Check for kills from activation (meteor, kamikaze, corruption, etc.)
        for fx in all_effects:
            if fx.get("type") == "capture" and fx.get("piece_type") == "king":
                killed_color = fx.get("color")
                if killed_color:
                    remaining = match.board.kings(Color(killed_color))
                    multi = match.tags.get(f"multi_king_{killed_color}", False)
                    if not multi or len(remaining) == 0:
                        winner = match.opponent_color(killed_color)
                        match_over = match.end_round(winner)
                        await _emit_round_over(sio, match, winner, match_over)
                        return

    # ── Disconnect Handling ──────────────────────────────────

    @sio.on("rumble:disconnect_check")
    async def on_rumble_disconnect(sid, data=None):
        """Called internally when a player disconnects."""
        match = room_manager.get_rumble_match_by_sid(sid)
        if match and not match.finished:
            await _handle_rumble_forfeit(sio, sid, match)


# ── Helper Functions ─────────────────────────────────────────

async def _emit_augment_proposals(sio: socketio.AsyncServer, match: RumbleMatch):
    """Send augment proposals to both players."""
    for color, sid in [("white", match.white_sid), ("black", match.black_sid)]:
        proposals = match.proposed[color]
        if match.selected.get(color) == "__skip__":
            await sio.emit("rumble:augment_phase", {
                "round": match.current_round,
                "proposals": [],
                "skipped": True,
                "scores": match.rounds_won,
                "my_augments": [a.to_dict() for a in match.augments[color]],
                "opponent_augments": [a.to_dict() for a in match.augments[match.opponent_color(color)]],
            }, to=sid)
        else:
            await sio.emit("rumble:augment_phase", {
                "round": match.current_round,
                "proposals": [a.to_dict() for a in proposals],
                "skipped": False,
                "scores": match.rounds_won,
                "my_augments": [a.to_dict() for a in match.augments[color]],
                "opponent_augments": [a.to_dict() for a in match.augments[match.opponent_color(color)]],
            }, to=sid)


async def _emit_round_start(sio: socketio.AsyncServer, match: RumbleMatch, effects: list[dict]):
    """Send round start data to both players."""
    for color, sid in [("white", match.white_sid), ("black", match.black_sid)]:
        state = match.get_board_state(color)
        entities = match.get_entities_for_viewer(color)
        opp = match.opponent_color(color)
        await sio.emit("rumble:round_start", {
            "round": match.current_round,
            "your_color": color,
            "state": state,
            "entities": entities,
            "effects": effects,
            "scores": match.rounds_won,
            "my_augments": [a.to_dict() for a in match.augments[color]],
            "opponent_augments": [a.to_dict() for a in match.augments[opp]],
            "white": match.white_username,
            "black": match.black_username,
        }, to=sid)


async def _emit_round_over(sio: socketio.AsyncServer, match: RumbleMatch,
                            winner: str, match_over: bool):
    """Announce round or match end."""
    payload = {
        "round_winner": winner,
        "scores": match.rounds_won,
        "round": match.current_round - (0 if match_over else 1),
        "match_over": match_over,
        "match_winner": match.match_winner,
    }
    await sio.emit("rumble:round_over", payload, to=match.white_sid)
    await sio.emit("rumble:round_over", payload, to=match.black_sid)

    if match_over:
        await _record_rumble_result(match)
    else:
        # Auto-start next augment phase after a delay (client handles display)
        match.phase = "augment_select"
        match.generate_proposals()
        await _emit_augment_proposals(sio, match)


async def _handle_rumble_forfeit(sio: socketio.AsyncServer, disconnected_sid: str, match: RumbleMatch):
    """Handle player disconnect during rumble match."""
    match.finished = True
    if disconnected_sid == match.white_sid:
        match.match_winner = "black"
        winner_sid = match.black_sid
    else:
        match.match_winner = "white"
        winner_sid = match.white_sid

    match.phase = "match_over"
    await sio.emit("rumble:round_over", {
        "round_winner": match.match_winner,
        "scores": match.rounds_won,
        "round": match.current_round,
        "match_over": True,
        "match_winner": match.match_winner,
        "reason": "opponent_disconnected",
    }, to=winner_sid)

    await _record_rumble_result(match)
    room_manager.remove_rumble_match(match.match_id)


async def _record_rumble_result(match: RumbleMatch):
    """Record rumble match result and update Elo."""
    db: Session = SessionLocal()
    try:
        white = db.query(User).filter(User.id == match.white_user_id).first()
        black = db.query(User).filter(User.id == match.black_user_id).first()
        if not white or not black:
            return

        winner_id = match.white_user_id if match.match_winner == "white" else match.black_user_id

        if match.match_winner == "white":
            new_w, new_b = compute_new_ratings(white.elo_rumble, black.elo_rumble)
        else:
            new_b, new_w = compute_new_ratings(black.elo_rumble, white.elo_rumble)

        record = Game(
            mode="rumble",
            white_id=white.id,
            black_id=black.id,
            winner_id=winner_id,
            white_elo_before=white.elo_rumble,
            black_elo_before=black.elo_rumble,
            white_elo_after=new_w,
            black_elo_after=new_b,
            ended_at=datetime.now(timezone.utc),
        )
        db.add(record)

        white.elo_rumble = new_w
        black.elo_rumble = new_b
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
