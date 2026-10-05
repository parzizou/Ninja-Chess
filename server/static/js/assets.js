// Sprite preloading. Missing images simply fall back to a drawn placeholder.

const PIECES = ["king", "queen", "bishop", "knight", "rook", "pawn", "licorne", "fantome", "sataniste", "tour_archer", "asassin"];
const images = new Map();

export const spriteUrl = (name) => `/assets/sprites/${name}.png`;

export function sprite(name) {
  const img = images.get(name);
  return img && img.complete && img.naturalWidth > 0 ? img : null;
}

export function loadAssets() {
  const names = ["duck"];
  for (const color of ["white", "black"]) for (const type of PIECES) names.push(`${color}_${type}`);
  return Promise.all(names.map((name) => new Promise((resolve) => {
    const img = new Image();
    img.onload = img.onerror = () => resolve();
    img.src = spriteUrl(name);
    images.set(name, img);
  })));
}
