// Local Player vs AI: no server involved, no Elo impact.

import { app, go, homeOrLogin } from "../app.js";
import { COOLDOWNS, computeMoves, isInCheck, opponentOf } from "../chess.js";
import * as sounds from "../sounds.js";
import { now } from "../util.js";
import { StandardGame } from "./standard_game.js";

const PIECE_VALUES = { pawn: 1, knight: 3, bishop: 3, rook: 5, queen: 9, king: 1000 };
const THINK_DELAYS = {
  easy: [1.8, 3.0],   // slow, same logic as medium but more hesitant
  medium: [0.8, 1.5], // greedy + king-safety awareness
  hard: [0.4, 0.7],   // fast but human-beatable: 1-ply gain/risk evaluation
};
const DIFF_LABELS = { easy: "Facile", medium: "Moyen", hard: "Difficile" };
const EP_WINDOW = 3; // seconds an en passant capture stays available
const BACK_RANK = ["rook", "knight", "bishop", "queen", "king", "bishop", "knight", "rook"];

const randomOf = (list) => list[Math.floor(Math.random() * list.length)];

function initialState() {
  const state = [];
  BACK_RANK.forEach((type, col) => {
    state.push({ type, color: "white", row: 0, col, alive: true });
    state.push({ type: "pawn", color: "white", row: 1, col, alive: true });
    state.push({ type: "pawn", color: "black", row: 6, col, alive: true });
    state.push({ type, color: "black", row: 7, col, alive: true });
  });
  return state;
}

class AiGame extends StandardGame {
  constructor(root, difficulty) {
    super(root, { myName: app.user ? app.user.username : "Vous" });
    this.difficulty = difficulty;
    this.aiColor = "black";
    this.thinkTimer = 0;
    this.epPawnPos = null;
    this.epExpires = 0;
    this.begin();
  }

  begin() {
    this.start({
      color: "white",
      opponent: `IA (${DIFF_LABELS[this.difficulty] || this.difficulty})`,
      state: initialState(),
    });
    this.epPawnPos = null;
    this.epExpires = 0;
    this.thinkTimer = 3 + 0.55 + 0.5; // countdown + fight flash + a short grace period
  }

  leave() { go(homeOrLogin()); }
  requestRematch() { this.begin(); }

  frame(dt) {
    super.frame(dt);
    if (!this.gameOver && !this.isLocked()) this.aiUpdate(dt);
  }

  get ctx() { return { rumble: false, aug: new Set() }; }
  movesOf(piece) { return computeMoves(this.view, piece, this.ctx); }

  // ── Player move ──────────────────────────────────────────

  executeMove(piece, fromRow, fromCol, toRow, toCol, promotion) {
    this.view.animateFrom(piece);
    this.view.stopDrag();
    this.view.clearSelection();

    if (this.applyMove(piece, fromRow, fromCol, toRow, toCol, this.myColor, promotion)) {
      this.showGameOver("Victoire !", true, "Rejouer ou retourner au menu");
      sounds.play("game_over_win");
      return;
    }
    this.scheduleThink();
  }

  scheduleThink() {
    const [lo, hi] = THINK_DELAYS[this.difficulty] || [0.5, 1];
    this.thinkTimer = lo + Math.random() * (hi - lo);
  }

  /** Applies a move locally. Returns true when a king was captured. */
  applyMove(piece, fromRow, fromCol, toRow, toCol, mover, promotion = null) {
    const t = now();
    const view = this.view;

    if (piece.type === "king" && Math.abs(toCol - fromCol) === 2) {
      const rookFrom = toCol > fromCol ? 7 : 0;
      const rookTo = toCol > fromCol ? 5 : 3;
      const rook = view.pieceAt(fromRow, rookFrom);
      if (rook) {
        view.animateFrom(rook);
        rook.col = rookTo;
        rook.lastMove = t;
      }
    }

    const ep = view.epSquare;
    const isEp = piece.type === "pawn" && fromCol !== toCol && !view.pieceAt(toRow, toCol)
      && ep && ep[0] === toRow && ep[1] === toCol && this.epExpires > t;
    if (isEp && this.epPawnPos) {
      const epPawn = view.pieceAt(this.epPawnPos[0], this.epPawnPos[1]);
      if (epPawn) {
        epPawn.alive = false;
        view.addCapture(epPawn.row, epPawn.col);
        sounds.play("capture");
      }
    }

    const captured = isEp ? null : view.pieceAt(toRow, toCol);
    if (captured && captured.alive) {
      captured.alive = false;
      view.addCapture(captured.row, captured.col);
      sounds.play("capture");
      if (captured.type === "king") {
        piece.row = toRow;
        piece.col = toCol;
        piece.cdTotal = COOLDOWNS[piece.type] ?? 1;
        piece.lastMove = t;
        return true;
      }
    }

    piece.row = toRow;
    piece.col = toCol;
    piece.cdTotal = COOLDOWNS[piece.type] ?? 1;
    piece.lastMove = t;
    sounds.play("move");

    if (piece.type === "pawn" && Math.abs(toRow - fromRow) === 2) {
      view.epSquare = [(fromRow + toRow) / 2, toCol];
      this.epPawnPos = [toRow, toCol];
      this.epExpires = t + EP_WINDOW;
    } else {
      view.epSquare = null;
      this.epPawnPos = null;
      this.epExpires = 0;
    }

    const promoRow = mover === "white" ? 7 : 0;
    if (piece.type === "pawn" && piece.row === promoRow) {
      piece.type = ["queen", "rook", "bishop", "knight"].includes(promotion) ? promotion : "queen";
      piece.cdTotal = COOLDOWNS[piece.type] ?? 5;
    }

    const foe = opponentOf(mover);
    if (isInCheck(view, foe)) {
      const king = view.pieces.find((p) => p.alive && p.type === "king" && p.color === foe);
      if (king) king.lastMove = 0;
    }
    return false;
  }

  // ── AI ───────────────────────────────────────────────────

  aiUpdate(dt) {
    if (this.thinkTimer > 0) {
      this.thinkTimer -= dt;
      return;
    }
    const available = this.view.pieces.filter((p) => p.alive && p.color === this.aiColor && !p.onCooldown());
    if (!available.length) {
      this.thinkTimer = 0.05; // everything on cooldown: poll again shortly
      return;
    }
    const move = this.pickMove(available);
    if (!move) {
      this.thinkTimer = 0.1;
      return;
    }
    const [piece, toRow, toCol] = move;
    this.view.animateFrom(piece);
    if (this.applyMove(piece, piece.row, piece.col, toRow, toCol, this.aiColor)) {
      this.showGameOver("Défaite...", false, "Rejouer ou retourner au menu");
      sounds.play("game_over_lose");
      return;
    }
    this.scheduleThink();
  }

  pickMove(available) {
    const all = [];
    for (const piece of available) {
      for (const [r, c] of this.movesOf(piece)) all.push([piece, r, c]);
    }
    if (!all.length) return null;
    if (this.difficulty === "easy") return this.greedyCapture(all);
    if (this.difficulty === "medium") return this.pickMedium(all);
    return this.pickHard(all);
  }

  /** Prefer taking the most valuable piece; otherwise random. */
  greedyCapture(moves) {
    const captures = [];
    for (const [piece, r, c] of moves) {
      const target = this.view.pieceAt(r, c);
      if (target && target.alive && target.color !== this.aiColor) {
        captures.push([PIECE_VALUES[target.type] ?? 0, piece, r, c]);
      }
    }
    if (captures.length) {
      const top = Math.max(...captures.map((c) => c[0]));
      return randomOf(captures.filter((c) => c[0] === top).map(([, p, r, c]) => [p, r, c]));
    }
    return randomOf(moves);
  }

  kingSafeAfter(piece, toR, toC) {
    const captured = this.view.pieceAt(toR, toC);
    const [oldR, oldC] = [piece.row, piece.col];
    piece.row = toR;
    piece.col = toC;
    if (captured) captured.alive = false;
    const safe = !isInCheck(this.view, this.aiColor);
    piece.row = oldR;
    piece.col = oldC;
    if (captured) captured.alive = true;
    return safe;
  }

  pickMedium(moves) {
    const safe = moves.filter((m) => this.kingSafeAfter(...m));
    let pool = safe.length ? safe : moves;
    if (isInCheck(this.view, this.aiColor)) {
      const escape = pool.filter((m) => this.kingSafeAfter(...m));
      if (escape.length) pool = escape;
    }
    return this.greedyCapture(pool);
  }

  pickHard(moves) {
    let bestScore = -Infinity;
    let best = [];
    for (const move of moves) {
      const score = this.scoreMove(...move);
      if (score === Infinity) return move;
      if (score > bestScore) { bestScore = score; best = [move]; }
      else if (score === bestScore) best.push(move);
    }
    return best.length ? randomOf(best) : randomOf(moves);
  }

  scoreMove(piece, toR, toC) {
    const captured = this.view.pieceAt(toR, toC);
    let gain = 0;
    if (captured && captured.alive) {
      if (captured.type === "king") return Infinity;
      gain = PIECE_VALUES[captured.type] ?? 0;
    }
    const [oldR, oldC] = [piece.row, piece.col];
    piece.row = toR;
    piece.col = toC;
    if (captured) captured.alive = false;

    let risk = 0;
    for (const foe of this.view.pieces) {
      if (!foe.alive || foe.color === this.aiColor) continue;
      if (this.movesOf(foe).some(([r, c]) => r === toR && c === toC)) {
        risk = PIECE_VALUES[piece.type] ?? 0;
        break;
      }
    }
    piece.row = oldR;
    piece.col = oldC;
    if (captured) captured.alive = true;
    return gain - risk;
  }
}

export default function mountAiGame(root, { difficulty = "medium" } = {}) {
  const game = new AiGame(root, difficulty);
  return () => game.destroy();
}
