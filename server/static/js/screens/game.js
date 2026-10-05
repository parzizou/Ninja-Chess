// Online standard game: the server validates every move; the client animates
// optimistically and rolls back if the move is refused.

import { app, go } from "../app.js";
import { COOLDOWNS, opponentOf } from "../chess.js";
import { emit, onMany } from "../socket.js";
import * as sounds from "../sounds.js";
import { now } from "../util.js";
import { StandardGame } from "./standard_game.js";

class OnlineGame extends StandardGame {
  constructor(root, init) {
    super(root, { myName: app.user.username });
    this.startFromRoom(init);

    this.disposer.add(onMany({
      "game:move_ack": (d) => this.onMoveAck(d),
      "game:opponent_move": (d) => this.onOpponentMove(d),
      "game:over": (d) => this.onGameOver(d),
      "game:rematch_waiting": () => this.setRematchState(true),
      "game:rematch_unavailable": () => this.setRematchState(false),
      // Sent again to both players when a rematch starts.
      "room:ready": (d) => this.startFromRoom(d),
    }));
  }

  startFromRoom(data) {
    const color = data.your_color || "white";
    this.start({
      color,
      opponent: (color === "white" ? data.black : data.white) || "",
      state: data.state || [],
    });
  }

  leave() {
    emit("room:leave");
    go("home");
  }

  requestRematch() {
    if (this.rematchWaiting) return;
    this.setRematchState(true);
    emit("game:rematch_request");
  }

  executeMove(piece, fromRow, fromCol, toRow, toCol, promotion) {
    this.view.animateFrom(piece);
    piece.row = toRow;
    piece.col = toCol;
    this.pending = { piece, fromRow, fromCol, toRow, toCol };
    this.view.stopDrag();
    this.view.clearSelection();

    const payload = { from_row: fromRow, from_col: fromCol, to_row: toRow, to_col: toCol };
    if (promotion) payload.promotion_piece = promotion;
    sounds.play("move");
    emit("game:move", payload);
  }

  onMoveAck(data) {
    if (!data.ok) {
      const p = this.pending;
      if (p) {
        if (p.piece.alive) {
          p.piece.row = p.fromRow;
          p.piece.col = p.fromCol;
          p.piece.animFrom = null;
          p.piece.animT = 1;
        }
        this.pending = null;
      }
      return;
    }

    // The mover, not whatever (captured) piece may still sit on the target square.
    const piece = this.pending ? this.pending.piece : this.view.pieceAt(data.to_row, data.to_col);
    if (piece) {
      piece.cdTotal = data.cooldown ?? COOLDOWNS[piece.type] ?? 1;
      piece.lastMove = now();
      if (data.promoted) {
        piece.type = data.promoted_to || "queen";
        piece.cdTotal = COOLDOWNS[piece.type] ?? 5;
      }
    }
    this.pending = null;

    if (data.captured) this.applyCapture(data.captured);
    if (data.castling_rook) this.applyCastlingRook(data.castling_rook);
    this.view.epSquare = data.en_passant_square || null;

    if (data.opponent_king_in_check) {
      const king = this.view.pieces.find((p) => p.alive && p.type === "king" && p.color === opponentOf(this.myColor));
      if (king) king.lastMove = 0;
      sounds.play("check");
    }
  }

  onOpponentMove(data) {
    const piece = this.view.pieceAt(data.from_row, data.from_col);
    if (piece) {
      this.view.animateFrom(piece);
      piece.row = data.to_row;
      piece.col = data.to_col;
      piece.cdTotal = data.cooldown ?? COOLDOWNS[piece.type] ?? 1;
      piece.lastMove = now();
      if (data.promoted) {
        piece.type = data.promoted_to || "queen";
        piece.cdTotal = COOLDOWNS[piece.type] ?? 5;
      }
    }
    if (data.captured) this.applyCapture(data.captured);
    if (data.castling_rook) this.applyCastlingRook(data.castling_rook);
    this.view.epSquare = data.en_passant_square || null;

    if (data.my_king_in_check) {
      const king = this.view.pieces.find((p) => p.alive && p.type === "king" && p.color === this.myColor);
      if (king) king.lastMove = 0;
      sounds.play("check");
    }
  }

  onGameOver(data) {
    const win = data.winner === this.myColor;
    sounds.play(win ? "game_over_win" : "game_over_lose");
    let text = win ? "Victoire !" : "Défaite...";
    if (data.reason === "opponent_disconnected") text += " (adversaire déconnecté)";
    this.showGameOver(text, win, "Lancez une revanche ou revenez au menu");
    // The opponent left: a rematch is impossible.
    if (data.reason === "opponent_disconnected") {
      this.replayBtn.disabled = true;
    }
  }
}

export default function mountGame(root, { init }) {
  const game = new OnlineGame(root, init);
  return () => game.destroy();
}
