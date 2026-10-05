// Rumble game screen: board + sidebars (profile & augments), score pips,
// augment activation (keys / targeting) and the visual effects emitted by the
// server for every augment.

import { app, go } from "../app.js";
import { BoardView, Piece } from "../board.js";
import { COOLDOWNS, computeMoves, opponentOf } from "../chess.js";
import { emit, onMany } from "../socket.js";
import * as sounds from "../sounds.js";
import { Disposer, h, now, startLoop, toast } from "../util.js";

const COUNTDOWN = 3;
const FIGHT_FLASH = 0.55;
const FREEZE = 1.5;        // board stays visible after a round ends…
const OVERLAY_TIME = 2.0;  // …then the result is shown before the next augment phase
const NUMBER_CODES = ["Digit1", "Digit2", "Digit3", "Digit4", "Digit5", "Digit6", "Digit7", "Digit8", "Digit9"];

class RumbleGame {
  constructor(root, data) {
    this.root = root;
    this.disposer = new Disposer();
    this.myName = app.user.username;

    this.myColor = data.your_color || "white";
    this.opponentName = (this.myColor === "white" ? data.black : data.white) || "Adversaire";
    this.round = data.round || 1;
    this.scores = data.scores || { white: 0, black: 0 };
    this.mine = data.my_augments || [];
    this.theirs = data.opponent_augments || [];

    this.pending = null;
    this.countdown = COUNTDOWN;
    this.fightFlash = FIGHT_FLASH;
    this.roundOver = false;
    this.matchOver = false;
    this.overTimer = 0;
    this.nextAugmentPhase = null;
    this.roundResult = "";
    this.targetingAugment = null;
    this.activationUsed = {}; // augment id -> last activation time
    this.fogTimers = {};      // color -> expiry
    this.keys = {};           // KeyboardEvent.code -> augment id
    this.cdRings = [];        // [{augment, el, label}] refreshed every frame

    this.buildDom();

    this.view = new BoardView(this.canvas, { theme: "rumble" }, {
      blocked: () => this.roundOver || this.isLocked(),
      canSelect: (p) => !p.onCooldown() && !p.stunned() && !p.tags.is_wall,
      getMoves: (p) => computeMoves(this.view, p, {
        rumble: true, aug: new Set(this.mine.map((a) => a.id)), myColor: this.myColor,
      }),
      tryMove: (p, r, c) => this.tryMove(p, r, c),
      onTarget: (r, c) => this.fireAtTarget(r, c),
    });
    this.disposer.add(() => this.view.destroy());
    this.view.myColor = this.myColor;
    this.view.entities = (data.entities || []).map((e) => ({ ...e }));
    this.view.setPieces((data.state || []).map((p) => new Piece({
      type: p.type, color: p.color, row: p.row, col: p.col, alive: p.alive,
      id: p.piece_id, tags: { ...(p.tags || {}), ...(p.fog_hidden ? { fog_hidden: true } : {}) },
    })));

    this.assignKeys();
    this.renderSidebars();
    this.renderScore();
    this.processEffects(data.effects || []);

    this.disposer.add(onMany({
      "rumble:move_ack": (d) => this.onMoveAck(d),
      "rumble:opponent_move": (d) => this.onOpponentMove(d),
      "rumble:round_over": (d) => this.onRoundOver(d),
      "rumble:activate_ack": (d) => this.onActivateAck(d),
      "rumble:augment_activated": (d) => this.processEffects(d.effects || []),
      "rumble:effects": (d) => this.processEffects(d.effects || []),
      "rumble:augment_phase": (d) => this.onAugmentPhase(d),
    }));
    this.disposer.listen(document, "keydown", (e) => this.onKey(e));
    this.disposer.add(startLoop((dt) => this.frame(dt)));
  }

  // ── DOM ──────────────────────────────────────────────────

  buildDom() {
    this.canvas = h("canvas", { class: "board-canvas", "aria-label": "Échiquier Rumble" });
    this.hint = h("div", { class: "target-hint", hidden: true, text: "Cliquez sur une cible... (Échap pour annuler)" });
    this.scoreBox = h("div", { class: "rumble-score" });
    this.leftList = h("ul", { class: "aug-list" });
    this.rightList = h("ul", { class: "aug-list" });

    this.countdownEl = h("div", { class: "countdown" });
    this.countdownLayer = h("div", { class: "overlay overlay-light", hidden: true }, this.countdownEl);
    this.overTitle = h("div", { class: "result" });
    this.overScore = h("p", { class: "score-line" });
    this.overNote = h("p", { class: "dim" });
    this.overMenu = h("button", { class: "btn btn-dim big", text: "Retour au menu", hidden: true, onclick: () => this.leave() });
    this.overLayer = h("div", { class: "overlay", hidden: true },
      h("div", { class: "modal center" }, this.overTitle, this.overScore, this.overNote, this.overMenu));

    const oppColor = opponentOf(this.myColor);
    this.root.append(
      h("div", { class: "rumble-screen" },
        h("div", { class: "rumble-top" },
          h("button", { class: "btn btn-danger small", text: "← Quitter", onclick: () => this.leave() }),
          this.scoreBox),
        h("div", { class: "rumble-main" },
          h("aside", { class: "rumble-side" },
            h("div", { class: "side-name", text: this.myName }),
            h("div", { class: "side-color", text: `(${this.myColor === "white" ? "blancs" : "noirs"})` }),
            h("div", { class: "side-title", text: "Augments actifs" }),
            this.leftList),
          h("div", { class: "board-col" },
            h("div", { class: "board-wrap" }, this.canvas),
            this.hint),
          h("aside", { class: "rumble-side" },
            h("div", { class: "side-name", text: this.opponentName }),
            h("div", { class: "side-color", text: `(${oppColor === "white" ? "blancs" : "noirs"})` }),
            h("div", { class: "side-title", text: "Augments actifs" }),
            this.rightList))),
      this.countdownLayer, this.overLayer,
    );
  }

  renderScore() {
    const oppColor = opponentOf(this.myColor);
    const group = (name, score) => h("div", { class: "score-group" },
      h("span", { class: "score-name", text: name.slice(0, 12) }),
      h("span", { class: "pips" }, [0, 1, 2].map((i) => h("span", { class: `pip ${i < score ? `on on-${i}` : ""}` }))));
    this.scoreBox.replaceChildren(
      group(this.myName, this.scores[this.myColor] || 0),
      h("span", { class: "score-sep" }),
      group(this.opponentName || "Adv.", this.scores[oppColor] || 0),
      h("span", { class: "score-round", text: `Manche ${this.round}` }),
    );
  }

  /** Key per activable augment: the one chosen at selection time, else the first free digit. */
  assignKeys() {
    this.keys = {};
    this.keyLabels = {};
    let digit = 0;
    for (const aug of this.mine) {
      if (!aug.is_activable) continue;
      const chosen = app.keybinds[aug.id];
      if (chosen) {
        this.keys[chosen.code] = aug.id;
        this.keyLabels[aug.id] = chosen.label;
      } else {
        while (digit < NUMBER_CODES.length && this.keys[NUMBER_CODES[digit]]) digit++;
        if (digit < NUMBER_CODES.length) {
          this.keys[NUMBER_CODES[digit]] = aug.id;
          this.keyLabels[aug.id] = String(digit + 1);
          digit++;
        }
      }
    }
  }

  renderSidebars() {
    this.cdRings = [];
    this.leftList.replaceChildren(...this.mine.map((aug) => {
      const label = this.keyLabels[aug.id];
      const text = h("span", { class: "aug-text", text: `${label ? `[${label}] ` : ""}${aug.name || "?"}` });
      const li = h("li", { class: `${aug.is_activable ? "activable" : ""} ${label ? "bound" : ""}`, title: aug.description || "" }, text);
      if (aug.is_activable) {
        const ring = h("span", { class: "cd-ring ready" });
        const remainingEl = h("span", { class: "cd-left" });
        li.append(remainingEl, ring);
        this.cdRings.push({ aug, ring, remainingEl });
      }
      return li;
    }));
    this.rightList.replaceChildren(...this.theirs.map((aug) =>
      h("li", { class: aug.is_activable ? "activable" : "", title: aug.description || "" },
        h("span", { class: "aug-text", text: aug.name || "?" }))));
  }

  // ── Frame loop ───────────────────────────────────────────

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

    if (this.roundOver) this.updateRoundOver(dt);

    // Fog of war expires on its own.
    const t = now();
    for (const color of Object.keys(this.fogTimers)) {
      if (t >= this.fogTimers[color]) {
        for (const p of this.view.pieces) if (p.color === color) delete p.tags.fog_hidden;
        delete this.fogTimers[color];
      }
    }

    this.updateCooldownRings(t);
    this.view.draw();
  }

  updateCountdown() {
    const show = this.isLocked() && !this.roundOver;
    this.countdownLayer.hidden = !show;
    if (!show) return;
    const s = performance.now() / 1000;
    if (this.countdown > 0) {
      const value = Math.max(1, Math.ceil(this.countdown));
      this.countdownEl.textContent = String(value);
      this.countdownEl.className = `countdown ${value === 1 ? "last" : ""}`;
      this.countdownEl.style.transform = `scale(${1 + 0.1 * Math.sin(s * 14)})`;
    } else {
      this.countdownEl.textContent = "FIGHT!";
      this.countdownEl.className = "countdown fight";
      this.countdownEl.style.transform = `scale(${1 + 0.08 * Math.sin(s * 18)})`;
    }
  }

  updateCooldownRings(t) {
    for (const { aug, ring, remainingEl } of this.cdRings) {
      const last = this.activationUsed[aug.id] || 0;
      const total = aug.cooldown || 0;
      const remaining = last > 0 && total > 0 ? Math.max(0, total - (t - last)) : 0;
      if (remaining > 0) {
        const frac = remaining / total;
        ring.className = "cd-ring";
        ring.style.background = `conic-gradient(rgb(200,70,70) ${frac * 360}deg, rgb(40,35,50) 0)`;
        remainingEl.textContent = `${Math.ceil(remaining)}s`;
      } else {
        ring.className = "cd-ring ready";
        ring.style.background = "";
        remainingEl.textContent = "";
      }
    }
  }

  updateRoundOver(dt) {
    this.overTimer += dt;
    this.overLayer.hidden = this.overTimer < FREEZE;
    if (!this.matchOver && this.nextAugmentPhase && this.overTimer >= FREEZE + OVERLAY_TIME) {
      const data = this.nextAugmentPhase;
      this.nextAugmentPhase = null;
      go("augment_select", { data });
    }
  }

  // ── Moves ────────────────────────────────────────────────

  tryMove(piece, toRow, toCol) {
    if (this.isLocked() || this.roundOver) return;
    if (piece.onCooldown() || piece.stunned() || this.pending) return;
    if (!this.view.isHighlighted(toRow, toCol)) return;

    const fromRow = piece.row, fromCol = piece.col;
    this.view.animateFrom(piece);
    piece.row = toRow;
    piece.col = toCol;
    this.pending = { piece, fromRow, fromCol, toRow, toCol };
    this.view.stopDrag();
    this.view.clearSelection();
    emit("rumble:move", { from_row: fromRow, from_col: fromCol, to_row: toRow, to_col: toCol });
  }

  onMoveAck(data) {
    if (!data.ok) {
      const p = this.pending;
      if (p) {
        if (p.piece.alive) {
          p.piece.row = p.fromRow;
          p.piece.col = p.fromCol;
          p.piece.animT = 1;
        }
        this.pending = null;
      }
      return;
    }

    // The mover, not the (captured) piece that may still sit on the target square.
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
    }
    this.processEffects(data.effects || []);

    // Drop any duplicate piece spawned on the promotion square.
    if (data.promoted && piece) {
      this.view.pieces = this.view.pieces.filter((p) =>
        !(p !== piece && p.alive && p.row === data.to_row && p.col === data.to_col));
    }
  }

  onOpponentMove(data) {
    const piece = this.view.pieceAt(data.from_row, data.from_col);
    if (piece) {
      delete piece.tags.fog_hidden; // moving reveals a piece hidden by fog
      this.view.animateFrom(piece);
      piece.row = data.to_row;
      piece.col = data.to_col;
      piece.cdTotal = data.cooldown ?? COOLDOWNS[piece.type] ?? 1;
      piece.lastMove = now();
      if (data.promoted) piece.type = data.promoted_to || "queen";
    }
    if (data.captured) this.applyCapture(data.captured);
    if (data.castling_rook) this.applyCastlingRook(data.castling_rook);
    this.view.epSquare = data.en_passant_square || null;

    if (data.my_king_in_check) {
      const king = this.view.pieces.find((p) => p.alive && p.type === "king" && p.color === this.myColor);
      if (king) king.lastMove = 0;
    }
    this.processEffects(data.effects || []);
  }

  applyCastlingRook(cr) {
    const rook = this.view.pieceAt(cr.row, cr.from_col);
    if (rook) {
      this.view.animateFrom(rook);
      rook.col = cr.to_col;
    }
  }

  /** Remove a captured piece. Accepts both piece dicts ("type") and effect dicts ("piece_type"). */
  applyCapture(cap) {
    const type = cap.piece_type || cap.type;
    for (const p of this.view.pieces) {
      if (p.alive && p.row === cap.row && p.col === cap.col && p.color === cap.color && p.type === type) {
        p.alive = false;
        this.view.addCapture(p.row, p.col);
        sounds.play("capture");
        break;
      }
    }
  }

  // ── Round / match flow ───────────────────────────────────

  onRoundOver(data) {
    this.roundOver = true;
    this.overTimer = 0;
    this.view.stopDrag();
    this.view.clearSelection();
    this.targetingAugment = null;
    this.view.targeting = false;
    this.hint.hidden = true;
    this.scores = data.scores || this.scores;
    this.matchOver = !!data.match_over;
    this.renderScore();

    const white = this.scores.white || 0, black = this.scores.black || 0;
    this.overScore.textContent = `Score : ${white} - ${black}`;
    if (this.matchOver) {
      const win = data.match_winner === this.myColor;
      this.overTitle.textContent = win ? "VICTOIRE DU MATCH !" : "DÉFAITE DU MATCH...";
      if (data.reason === "opponent_disconnected") this.overTitle.textContent += " (déconnexion)";
      this.overTitle.className = `result big ${win ? "win" : "lose"}`;
      this.overNote.textContent = "Appuyez sur Échap pour quitter";
      this.overMenu.hidden = false;
      sounds.play(win ? "game_over_win" : "game_over_lose");
    } else {
      const win = data.round_winner === this.myColor;
      this.overTitle.textContent = win ? "Manche gagnée !" : "Manche perdue...";
      this.overTitle.className = `result ${win ? "win" : "lose"}`;
      this.overNote.textContent = "Prochaine manche...";
      this.overMenu.hidden = true;
    }
  }

  /** The server sends the next augment phase right after round_over: let the result be seen first. */
  onAugmentPhase(data) {
    if (this.roundOver) this.nextAugmentPhase = data;
    else go("augment_select", { data });
  }

  leave() {
    emit("rumble:leave_room");
    go("home");
  }

  // ── Augment activation ───────────────────────────────────

  onKey(e) {
    if (e.key === "Escape") {
      if (this.roundOver && this.matchOver) { this.leave(); return; }
      this.view.stopDrag();
      this.view.clearSelection();
      this.setTargeting(null);
      return;
    }
    if (this.roundOver || this.isLocked() || e.repeat) return;
    const augId = this.keys[e.code];
    if (!augId) return;
    e.preventDefault();
    const aug = this.mine.find((a) => a.id === augId);
    if (!aug) return;
    if ((aug.target_type || "none") === "none") emit("rumble:activate", { augment_id: augId });
    else this.setTargeting(augId);
  }

  setTargeting(augId) {
    this.targetingAugment = augId;
    this.view.targeting = !!augId;
    this.hint.hidden = !augId;
    this.canvas.style.cursor = augId ? "crosshair" : "";
  }

  fireAtTarget(row, col) {
    const augId = this.targetingAugment;
    this.setTargeting(null);
    if (augId) emit("rumble:activate", { augment_id: augId, target_row: row, target_col: col });
  }

  onActivateAck(data) {
    if (data.ok) {
      this.activationUsed[data.augment_id || ""] = now();
      this.processEffects(data.effects || []);
      sounds.play("augment");
    } else if (data.reason) {
      toast(data.reason, "error", 2500);
    }
    this.setTargeting(null);
  }

  // ── Server effects ───────────────────────────────────────

  processEffects(effects) {
    const view = this.view;
    const byId = (id) => view.pieces.find((p) => p.id === id);
    const spawn = (fx, extra = {}) => view.pieces.push(new Piece({
      type: fx.piece_type, color: fx.color, row: fx.row, col: fx.col,
      lastMove: now(), id: fx.piece_id ?? 0, ...extra,
    }));
    const killAt = (row, col, effect = true) => {
      const p = view.pieces.find((q) => q.alive && q.row === row && q.col === col);
      if (p) {
        p.alive = false;
        if (effect) view.addCapture(p.row, p.col);
      }
    };

    for (const fx of effects) {
      switch (fx.type) {
        case "capture":
          this.applyCapture(fx);
          break;
        case "spawn":
          spawn(fx);
          break;
        case "transform": {
          const p = byId(fx.piece_id);
          if (p) p.tags.transformed = fx.visual || "";
          break;
        }
        case "stun": {
          const p = byId(fx.piece_id);
          if (p) p.tags.stun_until = now() + (fx.duration ?? 3);
          break;
        }
        case "teleport": {
          const p = byId(fx.piece_id);
          if (p) {
            view.animateFrom(p);
            p.row = fx.to_row;
            p.col = fx.to_col;
          }
          break;
        }
        case "swap":
          for (const p of view.pieces) {
            if (p.id === fx.piece1_id) {
              view.animateFrom(p);
              p.row = fx.p1_row;
              p.col = fx.p1_col;
            } else if (p.id === fx.piece2_id) {
              view.animateFrom(p);
              p.row = fx.p2_row;
              p.col = fx.p2_col;
            }
          }
          break;
        case "duck_place":
          view.entities = view.entities.filter((e) => !(e.type === "duck" && e.owner === fx.color));
          view.entities.push({ type: "duck", row: fx.row, col: fx.col, owner: fx.color || "" });
          break;
        case "trap_place":
          if (fx.color === this.myColor) view.entities.push({ type: "trap", row: fx.row, col: fx.col, owner: fx.color });
          break;
        case "trap_trigger":
          view.entities = view.entities.filter((e) => !(e.type === "trap" && e.row === fx.row && e.col === fx.col));
          view.addCapture(fx.row, fx.col, 0.8);
          break;
        case "sniper_shot": {
          const kr = fx.king_row ?? 0, kc = fx.king_col ?? 0;
          view.addLaser(kr, kc, (fx.direction ?? "up") === "up" ? 7 : 0, kc);
          break;
        }
        case "valkirie_pulse":
          view.addPulse(fx.queen_row ?? 0, fx.queen_col ?? 0);
          break;
        case "corruption": {
          const p = byId(fx.piece_id);
          if (p) {
            p.color = fx.new_color || p.color;
            p.lastMove = now();
          }
          break;
        }
        case "shadow_clone":
          spawn(fx, { tags: { is_clone: true } });
          break;
        case "meteor_warning":
          view.addCapture(fx.row, fx.col, 0.6);
          break;
        case "meteor_impact":
          view.addCapture(fx.row, fx.col, 0.6);
          killAt(fx.row, fx.col, false);
          break;
        case "kamikaze":
          killAt(fx.row, fx.col);
          break;
        case "cd_max": {
          const p = byId(fx.piece_id);
          if (p) p.lastMove = now();
          break;
        }
        case "cd_reset": {
          const p = byId(fx.piece_id);
          if (p) p.lastMove = 0;
          break;
        }
        case "micmic_mark": {
          const p = byId(fx.piece_id);
          if (p) p.tags.booby_trapped = true;
          break;
        }
        case "micmic_explode":
          view.addCapture(fx.row, fx.col);
          break;
        case "second_chance": {
          // The king survived: bring it back, stunned.
          const p = byId(fx.king_id);
          if (p) {
            p.alive = true;
            p.tags.stun_until = now() + 8;
          }
          break;
        }
        case "clone_capture": {
          const { captured_row: cr, captured_col: cc, piece_type: type, color } = fx;
          if (cr !== undefined && cr !== null && cc !== undefined && cc !== null && type && color) {
            const victim = view.pieces.find((p) => p.alive && p.row === cr && p.col === cc && p.type === type && p.color === color);
            if (victim) {
              victim.alive = false;
              view.addCapture(victim.row, victim.col);
            }
          }
          if (fx.clone_row !== undefined && fx.clone_row !== null && fx.clone_col !== undefined && fx.clone_col !== null) {
            view.pieces.push(new Piece({
              type: "pawn", color: fx.clone_color || this.myColor, row: fx.clone_row, col: fx.clone_col,
              lastMove: now(), tags: { is_clone: true },
            }));
          }
          break;
        }
        case "mark": {
          const p = byId(fx.piece_id);
          if (p) p.tags.marked_until = now() + (fx.duration ?? 8);
          break;
        }
        case "shield": {
          const p = byId(fx.piece_id);
          if (p) p.tags.shield_until = now() + (fx.duration ?? 5);
          break;
        }
        case "fog_start":
          if (fx.color && fx.color !== this.myColor) this.fogTimers[fx.color] = now() + (fx.duration ?? 10);
          break;
        case "promote": {
          const p = byId(fx.piece_id);
          if (p) {
            p.type = fx.to || "queen";
            p.cdTotal = COOLDOWNS[p.type] ?? 5;
          }
          break;
        }
        default:
          break;
      }
    }
  }

  destroy() { this.disposer.run(); }
}

export default function mountRumbleGame(root, { data }) {
  const game = new RumbleGame(root, data);
  return () => game.destroy();
}
