import { app, go, logout, refreshUser } from "../app.js";
import { spriteUrl } from "../assets.js";
import { h } from "../util.js";

const FLOATERS = [
  // [sprite, left %, top %, size px, delay s, duration s]
  ["white_knight", 8, 18, 54, 0, 7],
  ["black_bishop", 16, 52, 46, 1.1, 6],
  ["white_rook", 6, 78, 50, 2.3, 8],
  ["black_queen", 88, 20, 58, 0.5, 7],
  ["white_pawn", 82, 55, 38, 1.8, 5.5],
  ["black_king", 90, 80, 52, 3.1, 9],
];

export default function mountHome(root) {
  const eloLine = h("div", { class: "player-elo" });
  const setElo = () => {
    eloLine.textContent = `Standard  ${app.user.elo_standard}  •  Rumble  ${app.user.elo_rumble}`;
  };
  setElo();
  let alive = true;
  refreshUser().then(() => { if (alive) setElo(); });

  const menu = [
    ["⚔  Standard", "btn-blue", () => go("rooms")],
    ["🤖  Vs IA", "btn-green", () => go("ai_difficulty")],
    ["🔥  Rumble", "btn-rumble", () => go("rumble_rooms")],
    ["🏆  Classement", "btn-dim", () => go("leaderboard")],
    ["👤  Mon Profil", "btn-dim", () => go("profile")],
  ];

  root.append(
    h("div", { class: "home-bg" }),
    ...FLOATERS.map(([name, left, top, size, delay, dur]) =>
      h("img", {
        class: "floater", src: spriteUrl(name), alt: "",
        style: { left: `${left}%`, top: `${top}%`, width: `${size}px`, height: `${size}px`, animationDelay: `${-delay}s`, animationDuration: `${dur}s` },
      })),
    h("div", { class: "home-panel" },
      h("div", { class: "home-logo" },
        h("img", { src: "/assets/logo.png", alt: "Ninja Chess" })),
      h("div", { class: "home-rule" }),
      h("p", { class: "subtitle", text: "Échecs en temps réel simultané" }),
      h("div", { class: "player-card" },
        h("div", { class: "player-name", text: app.user.username }),
        eloLine),
      h("div", { class: "menu" },
        menu.map(([label, cls, fn]) => h("button", { class: `btn menu-btn ${cls}`, text: label, onclick: fn }))),
      h("button", { class: "btn btn-danger logout", text: "Déconnexion", onclick: () => logout() }),
      h("div", { class: "version", text: "v0.2 — fait avec ♥ pour les amis" }),
    ),
  );

  return () => { alive = false; };
}
