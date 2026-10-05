// Canvas board used by the standard game, the AI game and Rumble: pieces,
// cooldown overlays, drag & drop / click-to-move input and visual effects.
//
// Board coordinates: row 0 = white's back rank, col 0 = file a. The board is
// flipped when playing black so your own pieces are always at the bottom.

import { sprite } from "./assets.js";
import { COOLDOWNS, findAttackers, findKing } from "./chess.js";
import { now } from "./util.js";

export const SQ = 80;
export const SIZE = SQ * 8;
const ANIM_SPEED = 8;

const THEMES = {
  standard: { light: "rgb(240,217,181)", dark: "rgb(181,136,99)", border: "rgb(100,80,60)", highlight: "rgba(255,255,0,0.31)" },
  rumble: { light: "rgb(200,190,220)", dark: "rgb(110,90,140)", border: "rgb(140,100,180)", highlight: "rgba(255,200,50,0.35)" },
};

// Maps the server "visual" tag of a transformed piece to its sprite suffix.
const VISUAL_TO_SPRITE = {
  unicorn: "licorne",
  satanist: "sataniste",
  archer_tower: "tour_archer",
  ghost: "fantome",
  assassin: "asassin",
};

const SYMBOLS = {
  white: { king: "♔", queen: "♕", rook: "♖", bishop: "♗", knight: "♘", pawn: "♙" },
  black: { king: "♚", queen: "♛", rook: "♜", bishop: "♝", knight: "♞", pawn: "♟" },
};

export class Piece {
  constructor(d) {
    this.type = d.type;
    this.color = d.color;
    this.row = d.row;
    this.col = d.col;
    this.alive = d.alive !== false;
    this.cdTotal = d.cdTotal ?? COOLDOWNS[d.type] ?? 1;
    this.lastMove = d.lastMove ?? 0; // seconds since epoch of the last move, 0 = never
    this.id = d.id ?? 0;
    this.tags = d.tags ? { ...d.tags } : {};
    this.animFrom = null; // {x, y} canvas position the piece is sliding from
    this.animT = 1;
  }
  get spriteName() { return `${this.color}_${this.type}`; }
  onCooldown() { return this.lastMove !== 0 && now() - this.lastMove < this.cdTotal; }
  remaining() { return this.lastMove === 0 ? 0 : Math.max(0, this.cdTotal - (now() - this.lastMove)); }
  fraction() { return this.cdTotal > 0 ? this.remaining() / this.cdTotal : 0; }
  stunned() { return (this.tags.stun_until || 0) > now(); }
}

const rgba = (r, g, b, a) => `rgba(${r},${g},${b},${Math.max(0, Math.min(1, a))})`;

export class BoardView {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} opts  theme: "standard" | "rumble", showCheck: draw check warnings
   * @param {object} hooks blocked(), canSelect(piece), getMoves(piece), tryMove(piece,r,c), onTarget(r,c)
   */
  constructor(canvas, { theme = "standard", showCheck = false } = {}, hooks = {}) {
    this.canvas = canvas;
    this.theme = theme;
    this.colors = THEMES[theme];
    this.showCheck = showCheck;
    this.hooks = hooks;

    this.myColor = "white";
    this.pieces = [];
    this.entities = [];
    this.epSquare = null;

    this.selected = null;
    this.highlights = [];
    this.dragging = null;
    this.dragX = 0;
    this.dragY = 0;
    this.hoverSquare = null;
    this.targeting = false;

    this.captureEffects = [];
    this.laserEffects = [];
    this.pulseEffects = [];

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;
    this.g = canvas.getContext("2d");
    this.g.scale(dpr, dpr);

    this._onDown = (e) => this.onDown(e);
    this._onMove = (e) => this.onMove(e);
    this._onUp = (e) => this.onUp(e);
    this._onCancel = () => { this.stopDrag(); };
    canvas.addEventListener("pointerdown", this._onDown);
    canvas.addEventListener("pointermove", this._onMove);
    canvas.addEventListener("pointerup", this._onUp);
    canvas.addEventListener("pointercancel", this._onCancel);
    this._onContext = (e) => e.preventDefault();
    canvas.addEventListener("contextmenu", this._onContext);
  }

  destroy() {
    const c = this.canvas;
    c.removeEventListener("pointerdown", this._onDown);
    c.removeEventListener("pointermove", this._onMove);
    c.removeEventListener("pointerup", this._onUp);
    c.removeEventListener("pointercancel", this._onCancel);
    c.removeEventListener("contextmenu", this._onContext);
  }

  // ── State ────────────────────────────────────────────────

  setPieces(list) { this.pieces = list; }

  pieceAt(row, col) {
    return this.pieces.find((p) => p.alive && p.row === row && p.col === col) || null;
  }

  clearSelection() { this.selected = null; this.highlights = []; }

  stopDrag() { this.dragging = null; this.hoverSquare = null; }

  reset() {
    this.clearSelection();
    this.stopDrag();
    this.captureEffects = [];
    this.laserEffects = [];
    this.pulseEffects = [];
    this.epSquare = null;
    this.targeting = false;
  }

  // ── Coordinates ──────────────────────────────────────────

  /** Centre of a board square in canvas pixels. */
  toCanvas(row, col) {
    let r = row, c = col;
    if (this.myColor === "black") { r = 7 - row; c = 7 - col; }
    return [c * SQ + SQ / 2, (7 - r) * SQ + SQ / 2];
  }

  toBoard(x, y) {
    let col = Math.floor(x / SQ);
    let row = 7 - Math.floor(y / SQ);
    if (x < 0 || y < 0) return null;
    if (this.myColor === "black") { row = 7 - row; col = 7 - col; }
    return row >= 0 && row < 8 && col >= 0 && col < 8 ? [row, col] : null;
  }

  point(e) {
    const rect = this.canvas.getBoundingClientRect();
    return [(e.clientX - rect.left) * (SIZE / rect.width), (e.clientY - rect.top) * (SIZE / rect.height)];
  }

  /** Start sliding a piece from where it is drawn now (call before changing row/col). */
  animateFrom(piece) {
    const [x, y] = this.toCanvas(piece.row, piece.col);
    piece.animFrom = { x, y };
    piece.animT = 0;
  }

  // ── Input ────────────────────────────────────────────────

  onDown(e) {
    if (e.button !== 0 || (this.hooks.blocked && this.hooks.blocked())) return;
    const [x, y] = this.point(e);
    const sq = this.toBoard(x, y);

    if (this.targeting && sq) {
      this.hooks.onTarget?.(sq[0], sq[1]);
      return;
    }
    if (!sq) { this.stopDrag(); this.clearSelection(); return; }

    const [row, col] = sq;
    const clicked = this.pieceAt(row, col);
    if (clicked && clicked.color === this.myColor) {
      if (this.select(clicked)) {
        this.dragging = clicked;
        this.dragX = x;
        this.dragY = y;
        this.hoverSquare = sq;
        try { this.canvas.setPointerCapture(e.pointerId); } catch { /* ignore */ }
      }
      return;
    }
    if (this.selected && this.isHighlighted(row, col)) {
      this.hooks.tryMove?.(this.selected, row, col);
      return;
    }
    this.clearSelection();
  }

  onMove(e) {
    if (!this.dragging) return;
    if (this.hooks.blocked && this.hooks.blocked()) return;
    const [x, y] = this.point(e);
    this.dragX = x;
    this.dragY = y;
    this.hoverSquare = this.toBoard(x, y);
  }

  onUp(e) {
    if (e.button !== 0 || !this.dragging) return;
    try { this.canvas.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
    if (this.hooks.blocked && this.hooks.blocked()) { this.stopDrag(); return; }
    const piece = this.dragging;
    const [x, y] = this.point(e);
    const target = this.toBoard(x, y);
    this.stopDrag();
    if (target && this.selected === piece && this.isHighlighted(target[0], target[1])) {
      this.hooks.tryMove?.(piece, target[0], target[1]);
    }
  }

  isHighlighted(row, col) { return this.highlights.some(([r, c]) => r === row && c === col); }

  select(piece) {
    if (this.hooks.canSelect && !this.hooks.canSelect(piece)) return false;
    this.selected = piece;
    this.highlights = this.hooks.getMoves ? this.hooks.getMoves(piece) : [];
    return true;
  }

  // ── Effects ──────────────────────────────────────────────

  addCapture(row, col, duration) {
    const [x, y] = this.toCanvas(row, col);
    if (this.theme === "rumble") {
      const fragments = Array.from({ length: 8 }, (_, i) => [
        ((i * 45 + (Math.random() * 30 - 15)) * Math.PI) / 180,
        38 + Math.random() * 30,
      ]);
      this.captureEffects.push({ x, y, t: 0, duration: duration ?? 0.75, fragments });
    } else {
      this.captureEffects.push({ x, y, t: 0, duration: duration ?? 0.4 });
    }
  }

  addLaser(r1, c1, r2, c2) {
    const [x1, y1] = this.toCanvas(r1, c1);
    const [x2, y2] = this.toCanvas(r2, c2);
    this.laserEffects.push({ x1, y1, x2, y2, age: 0, duration: 0.45 });
  }

  addPulse(row, col) {
    const [cx, cy] = this.toCanvas(row, col);
    this.pulseEffects.push({ cx, cy, age: 0, duration: 0.6 });
  }

  update(dt) {
    for (const p of this.pieces) {
      if (p.animT < 1) p.animT = Math.min(1, p.animT + dt * ANIM_SPEED);
    }
    for (const list of ["captureEffects", "pulseEffects", "laserEffects"]) {
      for (const eff of this[list]) {
        if ("t" in eff) eff.t += dt; else eff.age += dt;
      }
      this[list] = this[list].filter((e) => ("t" in e ? e.t < e.duration : e.age < e.duration));
    }
  }

  // ── Drawing ──────────────────────────────────────────────

  draw() {
    const g = this.g;
    g.clearRect(0, 0, SIZE, SIZE);
    this.drawBoard();
    if (this.theme === "rumble") this.drawEntities();
    this.drawHighlights();
    this.drawPieces();
    if (this.showCheck) this.drawCheckIndicators();
    this.drawCaptureEffects();
    this.drawLasers();
    this.drawPulses();
  }

  drawBoard() {
    const g = this.g;
    for (let row = 0; row < 8; row++) {
      for (let col = 0; col < 8; col++) {
        const [x, y] = this.toCanvas(row, col);
        g.fillStyle = (row + col) % 2 === 0 ? this.colors.dark : this.colors.light;
        g.fillRect(x - SQ / 2, y - SQ / 2, SQ, SQ);
      }
    }
    g.strokeStyle = this.colors.border;
    g.lineWidth = 3;
    g.strokeRect(1.5, 1.5, SIZE - 3, SIZE - 3);
  }

  drawEntities() {
    const g = this.g;
    for (const ent of this.entities) {
      const [x, y] = this.toCanvas(ent.row, ent.col);
      if (ent.type === "duck") {
        const img = sprite("duck");
        if (img) g.drawImage(img, x - SQ * 0.425, y - SQ * 0.425, SQ * 0.85, SQ * 0.85);
        else {
          g.fillStyle = "rgb(255,220,50)";
          g.beginPath(); g.arc(x, y, SQ * 0.3, 0, Math.PI * 2); g.fill();
          this.text("D", x, y, 16, "rgb(80,60,0)", true);
        }
      } else if (ent.type === "trap" && ent.owner === this.myColor) {
        g.fillStyle = "rgba(200,50,50,0.4)";
        g.fillRect(x - SQ * 0.25, y - SQ * 0.25, SQ * 0.5, SQ * 0.5);
        this.text("T", x, y, 14, "rgba(255,100,100,0.6)");
      } else if (ent.type === "wall") {
        g.fillStyle = "rgb(100,100,110)";
        g.fillRect(x - SQ * 0.4, y - SQ * 0.4, SQ * 0.8, SQ * 0.8);
      }
    }
  }

  drawHighlights() {
    const g = this.g;
    const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 1000 * 7);
    const rumble = this.theme === "rumble";
    for (const [row, col] of this.highlights) {
      const [x, y] = this.toCanvas(row, col);
      g.fillStyle = this.colors.highlight;
      g.fillRect(x - SQ / 2, y - SQ / 2, SQ, SQ);
      g.fillStyle = rgba(255, 245, 180, 0.18);
      g.beginPath(); g.arc(x, y, SQ * (0.16 + 0.03 * pulse), 0, Math.PI * 2); g.fill();
      if (!rumble) {
        g.fillStyle = rgba(255, 250, 200, 0.7);
        g.beginPath(); g.arc(x, y, SQ * (0.06 + 0.012 * pulse), 0, Math.PI * 2); g.fill();
      }
    }
    if (this.hoverSquare && this.isHighlighted(this.hoverSquare[0], this.hoverSquare[1])) {
      const [x, y] = this.toCanvas(this.hoverSquare[0], this.hoverSquare[1]);
      g.strokeStyle = rgba(255, 245, 190, 0.86);
      g.lineWidth = 3;
      g.strokeRect(x - SQ * 0.44, y - SQ * 0.44, SQ * 0.88, SQ * 0.88);
    }
    if (this.selected) {
      const [x, y] = this.toCanvas(this.selected.row, this.selected.col);
      g.fillStyle = rgba(100, 200, 100, 0.31);
      g.fillRect(x - SQ / 2, y - SQ / 2, SQ, SQ);
    }
  }

  drawPieces() {
    const g = this.g;
    const dragged = this.dragging && this.dragging.alive ? this.dragging : null;
    const t = now();
    for (const piece of this.pieces) {
      if (!piece.alive || piece === dragged) continue;
      if (piece.tags.fog_hidden && piece.color !== this.myColor) continue;

      const [tx, ty] = this.toCanvas(piece.row, piece.col);
      let x = tx, y = ty;
      if (piece.animT < 1 && piece.animFrom) {
        x = piece.animFrom.x + (tx - piece.animFrom.x) * piece.animT;
        y = piece.animFrom.y + (ty - piece.animFrom.y) * piece.animT;
      }

      const mine = piece.color === this.myColor;
      const onCd = piece.onCooldown();
      const stunned = piece.stunned();
      const alpha = stunned ? 0.39 : mine && onCd ? 0.55 : 1;
      this.drawPiece(piece, x, y, alpha);

      if (onCd) this.drawCooldown(piece, x, y, mine);
      if (stunned) this.text("STUN", x, y - SQ * 0.35, 10, "rgb(255,50,50)", true);
      if (piece.tags.booby_trapped && mine) this.ring(x, y, SQ * 0.42, rgba(255, 50, 50, 0.78), 3);
      if ((piece.tags.marked_until || 0) > t) this.ring(x, y, SQ * 0.36, rgba(255, 140, 0, 0.86), 2);
      if ((piece.tags.shield_until || 0) > t) this.ring(x, y, SQ * 0.44, rgba(80, 140, 255, 0.86), 3);
      if (piece.tags.transformed) {
        this.text(String(piece.tags.transformed).slice(0, 3).toUpperCase(), x, y + SQ * 0.38, 9, "rgb(200,180,255)", true);
      }
    }
    if (dragged) this.drawPiece(dragged, this.dragX, this.dragY, 0.96, 1.08);
    g.globalAlpha = 1;
  }

  drawPiece(piece, x, y, alpha, mult = 1) {
    const g = this.g;
    const visual = piece.tags.transformed || "";
    const suffix = VISUAL_TO_SPRITE[visual];
    const img = suffix ? sprite(`${piece.color}_${suffix}`) : sprite(piece.spriteName) || sprite(piece.type);
    const size = SQ * 0.85 * mult;
    if (img) {
      g.globalAlpha = alpha;
      g.drawImage(img, x - size / 2, y - size / 2, size, size);
      g.globalAlpha = 1;
      return;
    }
    // Fallback when a sprite is missing: coloured disc with a chess glyph.
    const white = piece.color === "white";
    g.globalAlpha = alpha;
    g.fillStyle = white ? "rgb(240,240,240)" : "rgb(50,50,50)";
    g.beginPath(); g.arc(x, y, SQ * 0.35 * mult, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "rgba(0,0,0,0.4)"; g.lineWidth = 2; g.stroke();
    const glyph = (SYMBOLS[piece.color] || SYMBOLS.white)[piece.type] || piece.type[0].toUpperCase();
    this.text(glyph, x, y, 28 * mult, white ? "rgb(30,30,30)" : "rgb(230,230,230)");
    g.globalAlpha = 1;
  }

  ring(x, y, r, color, width) {
    const g = this.g;
    g.strokeStyle = color;
    g.lineWidth = width;
    g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.stroke();
  }

  text(str, x, y, size, color, bold = false) {
    const g = this.g;
    g.fillStyle = color;
    g.font = `${bold ? "bold " : ""}${size}px system-ui, "Segoe UI Symbol", sans-serif`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(str, x, y);
  }

  drawCooldown(piece, x, y, mine) {
    const frac = piece.fraction();
    if (frac <= 0) return;
    const g = this.g;
    if (mine) {
      const radius = SQ * 0.4;
      const segments = 32;
      const span = 360 * frac;
      const pts = [];
      for (let i = 0; i <= segments; i++) {
        const a = ((90 - (span * i) / segments) * Math.PI) / 180;
        pts.push([x + radius * Math.cos(a), y - radius * Math.sin(a)]);
      }
      g.fillStyle = rgba(200, 60, 60, 0.31);
      g.beginPath();
      g.moveTo(x, y);
      for (const [px, py] of pts) g.lineTo(px, py);
      g.closePath();
      g.fill();
      if (this.theme === "standard") {
        g.strokeStyle = rgba(200, 60, 60, 0.7);
        g.lineWidth = 3;
        g.beginPath();
        pts.forEach(([px, py], i) => (i ? g.lineTo(px, py) : g.moveTo(px, py)));
        g.stroke();
      }
    } else {
      const bx = x + SQ * 0.3, by = y - SQ * 0.35;
      g.fillStyle = rgba(200, 50, 50, 0.78);
      g.beginPath(); g.arc(bx, by, 12, 0, Math.PI * 2); g.fill();
      this.text(piece.remaining().toFixed(1), bx, by, 10, "#fff", true);
    }
  }

  drawCaptureEffects() {
    const g = this.g;
    for (const eff of this.captureEffects) {
      const t = eff.t / eff.duration;
      if (!eff.fragments) {
        const radius = 20 + 30 * t;
        g.fillStyle = rgba(255, 100, 50, 1 - t);
        g.beginPath(); g.arc(eff.x, eff.y, radius, 0, Math.PI * 2); g.fill();
        g.strokeStyle = rgba(255, 200, 100, 1 - t);
        g.lineWidth = 2; g.stroke();
        continue;
      }
      const flash = Math.min(1, t * 4);
      if (flash < 1) {
        g.strokeStyle = rgba(255, 240, 100, 1 - flash);
        g.lineWidth = 4;
        g.beginPath(); g.arc(eff.x, eff.y, 8 + 36 * flash, 0, Math.PI * 2); g.stroke();
      }
      const core = 0.86 * Math.max(0, 1 - t * 1.5);
      if (core > 0) {
        g.fillStyle = rgba(255, 140, 40, core);
        g.beginPath(); g.arc(eff.x, eff.y, Math.max(2, 14 * (1 - t)), 0, Math.PI * 2); g.fill();
      }
      for (const [angle, speed] of eff.fragments) {
        const dist = speed * t;
        const size = Math.max(1, 7 * (1 - t));
        const a = Math.max(0, 1 - t * 1.2);
        if (a <= 0) continue;
        g.fillStyle = rgba(255, Math.round(180 * (1 - t * 0.5)), 60, a);
        g.fillRect(eff.x + Math.cos(angle) * dist - size / 2, eff.y - Math.sin(angle) * dist - size / 2, size, size);
      }
    }
  }

  drawLasers() {
    const g = this.g;
    for (const eff of this.laserEffects) {
      const t = eff.age / eff.duration;
      const a = Math.max(0, 1 - t * 1.4);
      if (a <= 0) continue;
      const line = (color, width) => {
        g.strokeStyle = color; g.lineWidth = width;
        g.beginPath(); g.moveTo(eff.x1, eff.y1); g.lineTo(eff.x2, eff.y2); g.stroke();
      };
      line(rgba(255, 200, 80, a / 4), 12);
      line(rgba(255, 240, 140, a / 2), 5);
      line(rgba(255, 255, 255, a), 2);
      if (t < 0.3) {
        g.fillStyle = rgba(255, 230, 120, 0.86 * (1 - t / 0.3));
        g.beginPath(); g.arc(eff.x1, eff.y1, 8 * (1 - t / 0.3), 0, Math.PI * 2); g.fill();
      }
    }
  }

  drawPulses() {
    for (const eff of this.pulseEffects) {
      const t = eff.age / eff.duration;
      for (let i = 0; i < 3; i++) {
        const rt = t - i * 0.15;
        if (rt <= 0) continue;
        const a = 0.78 * Math.max(0, 1 - rt * 1.3);
        if (a <= 0) continue;
        this.ring(eff.cx, eff.cy, rt * 120, rgba(200, 140, 255, a), Math.max(1, Math.round(4 * (1 - rt))));
      }
    }
  }

  drawCheckIndicators() {
    const g = this.g;
    const pulse = 0.5 + 0.5 * Math.sin((Date.now() / 1000) * 6);
    for (const color of ["white", "black"]) {
      const attackers = findAttackers(this, color);
      if (!attackers.length) continue;
      const king = findKing(this, color);
      if (!king) continue;
      const [kx, ky] = this.toCanvas(king.row, king.col);
      g.fillStyle = rgba(220, 20, 20, (90 + 60 * pulse) / 255);
      g.fillRect(kx - SQ / 2, ky - SQ / 2, SQ, SQ);
      this.ring(kx, ky, SQ * (0.42 + 0.08 * pulse), rgba(255, 60, 60, 0.78), 3);
      for (const att of attackers.slice(0, 2)) {
        const [ax, ay] = this.toCanvas(att.row, att.col);
        this.threatArrow(ax, ay, kx, ky);
      }
    }
  }

  threatArrow(x1, y1, x2, y2) {
    const g = this.g;
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.hypot(dx, dy);
    if (len < 1) return;
    const nx = dx / len, ny = dy / len;
    const pad = SQ * 0.4;
    const sx = x1 + nx * pad, sy = y1 + ny * pad;
    const ex = x2 - nx * pad, ey = y2 - ny * pad;
    g.strokeStyle = rgba(255, 80, 80, 0.78);
    g.lineWidth = 3;
    g.beginPath(); g.moveTo(sx, sy); g.lineTo(ex, ey); g.stroke();
    for (const side of [0.45, -0.45]) {
      const angle = Math.atan2(ny, nx) + Math.PI + side;
      g.beginPath();
      g.moveTo(ex, ey);
      g.lineTo(ex + 12 * Math.cos(angle), ey + 12 * Math.sin(angle));
      g.stroke();
    }
  }
}
