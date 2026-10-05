// Standard-mode game screen shared by the online game and the local AI game.
// Subclasses provide: executeMove(), leave(), requestRematch(), and call
// start() with the initial position.

import { BoardView, Piece } from "../board.js";
import { computeMoves } from "../chess.js";
import { spriteUrl } from "../assets.js";
import * as sounds from "../sounds.js";
import { Disposer, h, startLoop } from "../util.js";

const COUNTDOWN = 3;
const FIGHT_FLASH = 0.55;
const PROMOTIONS = [["queen", "Dame"], ["rook", "Tour"], ["bishop", "Fou"], ["knight", "Cavalier"]];
const NO_AUG = new Set();

export class StandardGame {
  constructor(root, { myName }) {
    this.root = root;
    this.myName = myName;
    this.disposer = new Disposer();

    this.myColor = "white";
    this.opponentName = "";
    this.pending = null;      // optimistic move waiting for the server ack
    this.promo = null;        // pawn promotion waiting for a choice
    this.gameOver = false;
    this.rematchWaiting = false;
    this.countdown = COUNTDOWN;
    this.fightFlash = FIGHT_FLASH;

    this.buildDom();

    this.view = new BoardView(this.canvas, { theme: "standard", showCheck: true }, {
      blocked: () => this.isLocked() || this.gameOver || !!this.promo,
      canSelect: (piece) => !piece.onCooldown(),
      getMoves: (piece) => computeMoves(this.view, piece),
      tryMove: (piece, r, c) => this.tryMove(piece, r, c),
    });
    this.disposer.add(() => this.view.destroy());

    this.disposer.listen(document, "keydown", (e) => this.onKey(e));
    this.disposer.add(startLoop((dt) => this.frame(dt)));
  }

  // ── DOM ──────────────────────────────────────────────────

  buildDom() {
    this.canvas = h("canvas", { class: "board-canvas", "aria-label": "Échiquier" });
    this.oppLabel = h("div", { class: "game-info" });
    this.meLabel = h("div", { class: "game-info" });
    this.countdownEl = h("div", { class: "countdown" });
    this.countdownLayer = h("div", { class: "overlay overlay-light", hidden: true }, this.countdownEl);

    this.resultEl = h("div", { class: "result" });
    this.resultHint = h("p", { class: "dim" });
    this.replayBtn = h("button", { class: "btn btn-green big", onclick: () => this.requestRematch() });
    this.menuBtn = h("button", { class: "btn btn-dim big", text: "Menu", onclick: () => this.leave() });
    this.rematchNote = h("p", { class: "dim" });
    this.overOverlay = h("div", { class: "overlay", hidden: true },
      h("div", { class: "modal center" }, this.resultEl, this.resultHint,
        h("div", { class: "row" }, this.replayBtn, this.menuBtn), this.rematchNote));

    this.promoRow = h("div", { class: "promo-row" });
    this.promoOverlay = h("div", { class: "overlay", hidden: true },
      h("div", { class: "modal center" }, h("h3", { text: "Choisir la promotion" }), this.promoRow));

    this.root.append(
      h("div", { class: "game-screen" },
        h("div", { class: "game-top" },
          h("button", { class: "btn btn-danger small", text: "← Quitter", onclick: () => this.leave() }),
          this.oppLabel),
        h("div", { class: "board-wrap" }, this.canvas),
        h("div", { class: "game-bottom" }, this.meLabel)),
      this.countdownLayer, this.promoOverlay, this.overOverlay,
    );
  }

  // ── Lifecycle ────────────────────────────────────────────

  /** (Re)start a game from a server-style state list. */
  start({ color, opponent, state }) {
    this.view.reset();
    this.pending = null;
    this.promo = null;
    this.gameOver = false;
    this.rematchWaiting = false;
    this.countdown = COUNTDOWN;
    this.fightFlash = FIGHT_FLASH;
    this.myColor = color;
    this.opponentName = opponent;
    this.view.myColor = color;
    this.view.setPieces(state.map((p) => new Piece({
      type: p.type, color: p.color, row: p.row, col: p.col, alive: p.alive,
    })));
    this.oppLabel.textContent = `Adversaire : ${opponent}`;
    this.meLabel.textContent = `${this.myName} (${color === "white" ? "blancs" : "noirs"})`;
    this.promoOverlay.hidden = true;
    this.overOverlay.hidden = true;
    this.setRematchState(false);
  }

  destroy() { this.disposer.run(); }

  isLocked() { return this.countdown > 0 || this.fightFlash > 0; }

  frame(dt) {
    this.view.update(dt);
    if (this.countdown > 0) {
      this.countdown = Math.max(0, this.countdown - dt);
      if (this.countdown === 0) sounds.play("round_start");
    } else if (this.fightFlash > 0) {
      this.fightFlash = Math.max(0, this.fightFlash - dt);
    }
    this.updateCountdown();
    this.view.draw();
  }

  updateCountdown() {
    const show = this.isLocked() && !this.gameOver;
    this.countdownLayer.hidden = !show;
    if (!show) return;
    const t = performance.now() / 1000;
    if (this.countdown > 0) {
      const value = Math.max(1, Math.ceil(this.countdown));
      this.countdownEl.textContent = String(value);
      this.countdownEl.className = `countdown ${value === 1 ? "last" : ""}`;
      this.countdownEl.style.transform = `scale(${1 + 0.1 * Math.sin(t * 14)})`;
    } else {
      this.countdownEl.textContent = "FIGHT!";
      this.countdownEl.className = "countdown fight";
      this.countdownEl.style.transform = `scale(${1 + 0.08 * Math.sin(t * 18)})`;
    }
  }

  // ── Moves ────────────────────────────────────────────────

  tryMove(piece, toRow, toCol) {
    if (this.isLocked() || piece.onCooldown() || this.pending) return;
    if (!this.view.isHighlighted(toRow, toCol)) return;

    const promoRow = this.myColor === "white" ? 7 : 0;
    if (piece.type === "pawn" && toRow === promoRow) {
      this.promo = { piece, fromRow: piece.row, fromCol: piece.col, toRow, toCol };
      this.view.stopDrag();
      this.view.clearSelection();
      this.showPromo(piece.color);
      return;
    }
    this.executeMove(piece, piece.row, piece.col, toRow, toCol, null);
  }

  showPromo(color) {
    this.promoRow.replaceChildren(...PROMOTIONS.map(([type, label]) =>
      h("button", { class: "promo-btn", onclick: () => this.confirmPromo(type) },
        h("img", { src: spriteUrl(`${color}_${type}`), alt: label, width: "56", height: "56" }),
        h("span", { text: label }))));
    this.promoOverlay.hidden = false;
  }

  confirmPromo(type) {
    const p = this.promo;
    this.promo = null;
    this.promoOverlay.hidden = true;
    if (p) this.executeMove(p.piece, p.fromRow, p.fromCol, p.toRow, p.toCol, type);
  }

  cancelPromo() {
    this.promo = null;
    this.promoOverlay.hidden = true;
  }

  /** Subclass hook: apply the move (optimistically) and tell whoever is in charge. */
  executeMove() { throw new Error("executeMove not implemented"); }
  leave() { throw new Error("leave not implemented"); }
  requestRematch() { throw new Error("requestRematch not implemented"); }

  // ── Shared effects ───────────────────────────────────────

  applyCapture(cap) {
    for (const p of this.view.pieces) {
      if (p.alive && p.row === cap.row && p.col === cap.col && p.color === cap.color && p.type === cap.type) {
        p.alive = false;
        this.view.addCapture(p.row, p.col);
        sounds.play("capture");
        break;
      }
    }
  }

  applyCastlingRook(cr) {
    const rook = this.view.pieceAt(cr.row, cr.from_col);
    if (rook) {
      this.view.animateFrom(rook);
      rook.col = cr.to_col;
    }
  }

  // ── Game over / rematch ──────────────────────────────────

  showGameOver(text, win, hint) {
    this.gameOver = true;
    this.view.stopDrag();
    this.view.clearSelection();
    this.resultEl.textContent = text;
    this.resultEl.className = `result ${win ? "win" : "lose"}`;
    this.resultHint.textContent = hint;
    this.setRematchState(false);
    this.overOverlay.hidden = false;
  }

  setRematchState(waiting) {
    this.rematchWaiting = waiting;
    this.replayBtn.disabled = waiting;
    this.replayBtn.textContent = waiting ? "En attente..." : "Rejouer";
    this.rematchNote.textContent = waiting ? "En attente de l'adversaire..." : "";
  }

  onKey(e) {
    if (e.key !== "Escape") return;
    if (this.gameOver) this.leave();
    else if (this.promo) this.cancelPromo();
    else {
      this.view.stopDrag();
      this.view.clearSelection();
    }
  }
}
