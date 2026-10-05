// Client-side move generation, used only for highlighting legal squares and by
// the local AI. The server stays authoritative for every online move.
//
// `view` is anything exposing: pieceAt(row, col), entities (array of
// {type,row,col}) and epSquare ([row, col] | null) — i.e. a BoardView.
//
// ctx = { rumble: bool, aug: Set<string> (my augment ids), myColor }

export const COOLDOWNS = { pawn: 1.5, knight: 3, bishop: 3, rook: 4, queen: 5, king: 3 };

export const opponentOf = (color) => (color === "white" ? "black" : "white");

const sign = (n) => (n > 0 ? 1 : n < 0 ? -1 : 0);
const blockers = (view) => (view.entities || []).filter((e) => e.type === "duck" || e.type === "wall");

export function pathClear(view, piece, dr, dc) {
  const sr = sign(dr), sc = sign(dc);
  const steps = Math.max(Math.abs(dr), Math.abs(dc));
  const walls = blockers(view);
  for (let i = 1; i < steps; i++) {
    const r = piece.row + sr * i, c = piece.col + sc * i;
    if (view.pieceAt(r, c)) return false;
    if (walls.some((e) => e.row === r && e.col === c)) return false;
  }
  return true;
}

/** Ghost bishop: passes through allies, stopped by the first enemy. */
function ghostPathClear(view, piece, dr, dc) {
  const sr = sign(dr), sc = sign(dc);
  const steps = Math.max(Math.abs(dr), Math.abs(dc));
  for (let i = 1; i < steps; i++) {
    const mid = view.pieceAt(piece.row + sr * i, piece.col + sc * i);
    if (mid && mid.color !== piece.color) return false;
  }
  return true;
}

function canCastle(view, king, dc) {
  if (king.lastMove !== 0) return false;
  const rookCol = dc > 0 ? 7 : 0;
  const pathCols = dc > 0 ? [5, 6] : [1, 2, 3];
  const rook = view.pieceAt(king.row, rookCol);
  if (!rook || rook.type !== "rook" || rook.color !== king.color) return false;
  if (rook.lastMove !== 0) return false;
  return pathCols.every((c) => !view.pieceAt(king.row, c));
}

function basicValid(view, piece, toR, toC, target, ctx) {
  const dr = toR - piece.row;
  const dc = toC - piece.col;
  const diag = Math.abs(dr) === Math.abs(dc) && dr !== 0;
  const straight = (dr === 0) !== (dc === 0);
  const transformed = (piece.tags && piece.tags.transformed) || "";
  const rumble = ctx.rumble;

  switch (piece.type) {
    case "pawn": {
      const dir = piece.color === "white" ? 1 : -1;
      const startRow = piece.color === "white" ? 1 : 6;
      if (dc === 0 && dr === dir && !target) return true;
      if (dc === 0 && dr === 2 * dir && !target) {
        const clear = !view.pieceAt(piece.row + dir, piece.col);
        if (piece.row === startRow && clear) return true;
        if (rumble && ctx.aug.has("sprinteurs") && clear) return true;
      }
      if (Math.abs(dc) === 1 && dr === dir && target) return true;
      const ep = view.epSquare;
      if (Math.abs(dc) === 1 && dr === dir && !target && ep && ep[0] === toR && ep[1] === toC) return true;
      if (rumble && ctx.aug.has("marche_arriere")) {
        if (dc === 0 && dr === -dir && !target) return true;
        if (Math.abs(dc) === 1 && dr === -dir && target) return true;
      }
      return false;
    }
    case "knight": {
      const L = (Math.abs(dr) === 2 && Math.abs(dc) === 1) || (Math.abs(dr) === 1 && Math.abs(dc) === 2);
      if (L) return true;
      if (!rumble) return false;
      if (transformed === "unicorn" && diag) return pathClear(view, piece, dr, dc);
      if (transformed === "assassin") {
        const enemyBack = piece.color === "white" ? 7 : 0;
        if (toR === enemyBack && !target) return true;
      }
      return false;
    }
    case "bishop": {
      if (rumble && transformed === "ghost") return diag && ghostPathClear(view, piece, dr, dc);
      if (diag) return pathClear(view, piece, dr, dc);
      if (rumble && transformed === "satanist" && dc === 0) {
        const dir = piece.color === "white" ? 1 : -1;
        if (dr === dir) return !!target;
        if (dr === 2 * dir) return !!target && !view.pieceAt(piece.row + dir, piece.col);
      }
      return false;
    }
    case "rook": {
      if (straight) return pathClear(view, piece, dr, dc);
      if (rumble && transformed === "archer_tower" && diag) {
        if (Math.abs(dr) === 1) return !!target;
        if (Math.abs(dr) === 2) {
          const mid = view.pieceAt(piece.row + sign(dr), piece.col + sign(dc));
          return !!target && !mid;
        }
      }
      return false;
    }
    case "queen":
      return (diag || straight) && pathClear(view, piece, dr, dc);
    case "king":
      if (Math.max(Math.abs(dr), Math.abs(dc)) === 1) return true;
      if (dr === 0 && Math.abs(dc) === 2) return rumble ? true : canCastle(view, piece, dc);
      return false;
    default:
      return false;
  }
}

/** Transition augment: the king slides like a queen, the queen steps like a king. */
function transitionMoves(view, piece) {
  const moves = [];
  const walls = new Set(blockers(view).map((e) => `${e.row},${e.col}`));
  if (piece.type === "king") {
    for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [-1, 1], [1, -1], [1, 1]]) {
      for (let dist = 1; dist < 8; dist++) {
        const r = piece.row + dr * dist, c = piece.col + dc * dist;
        if (r < 0 || r > 7 || c < 0 || c > 7) break;
        if (walls.has(`${r},${c}`)) break;
        const target = view.pieceAt(r, c);
        if (target) {
          if (target.color !== piece.color) moves.push([r, c]);
          break;
        }
        moves.push([r, c]);
      }
    }
  } else {
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        if (!dr && !dc) continue;
        const r = piece.row + dr, c = piece.col + dc;
        if (r < 0 || r > 7 || c < 0 || c > 7 || walls.has(`${r},${c}`)) continue;
        const target = view.pieceAt(r, c);
        if (!target || target.color !== piece.color) moves.push([r, c]);
      }
    }
  }
  return moves;
}

export function computeMoves(view, piece, ctx = { rumble: false, aug: new Set() }) {
  if (ctx.rumble && piece.color === ctx.myColor && ctx.aug.has("transition")
      && (piece.type === "king" || piece.type === "queen")) {
    return transitionMoves(view, piece);
  }
  const walls = ctx.rumble ? blockers(view) : [];
  const moves = [];
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      if (r === piece.row && c === piece.col) continue;
      const target = view.pieceAt(r, c);
      if (target && target.color === piece.color) continue;
      if (walls.some((e) => e.row === r && e.col === c)) continue;
      if (basicValid(view, piece, r, c, target, ctx)) moves.push([r, c]);
    }
  }
  return moves;
}

/** Can `attacker` hit (r, c)? Used for check detection (no castling / en passant). */
export function canAttack(view, attacker, r, c) {
  const dr = r - attacker.row, dc = c - attacker.col;
  const diag = Math.abs(dr) === Math.abs(dc) && dr !== 0;
  const straight = (dr === 0) !== (dc === 0);
  switch (attacker.type) {
    case "pawn": return Math.abs(dc) === 1 && dr === (attacker.color === "white" ? 1 : -1);
    case "knight": return (Math.abs(dr) === 2 && Math.abs(dc) === 1) || (Math.abs(dr) === 1 && Math.abs(dc) === 2);
    case "bishop": return diag && pathClear(view, attacker, dr, dc);
    case "rook": return straight && pathClear(view, attacker, dr, dc);
    case "queen": return (diag || straight) && pathClear(view, attacker, dr, dc);
    case "king": return Math.abs(dr) <= 1 && Math.abs(dc) <= 1;
    default: return false;
  }
}

export function findKing(view, color) {
  return view.pieces.find((p) => p.alive && p.type === "king" && p.color === color) || null;
}

export function findAttackers(view, kingColor) {
  const king = findKing(view, kingColor);
  if (!king) return [];
  const foe = opponentOf(kingColor);
  return view.pieces.filter((p) => p.alive && p.color === foe && canAttack(view, p, king.row, king.col));
}

export const isInCheck = (view, color) => findAttackers(view, color).length > 0;
