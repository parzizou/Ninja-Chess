// Sound effects (short WAV files). Browsers only allow audio after a user
// gesture; play() failures are silently ignored.

const NAMES = ["move", "capture", "check", "game_over_win", "game_over_lose", "augment", "round_start"];
const audio = new Map();

for (const name of NAMES) {
  const el = new Audio(`/assets/sounds/${name}.wav`);
  el.preload = "auto";
  audio.set(name, el);
}

export function play(name, volume = 0.6) {
  const base = audio.get(name);
  if (!base) return;
  try {
    const el = base.cloneNode();
    el.volume = volume;
    el.play().catch(() => {});
  } catch { /* ignore */ }
}
