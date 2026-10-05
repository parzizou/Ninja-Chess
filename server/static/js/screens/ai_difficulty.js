import { go, homeOrLogin } from "../app.js";
import { h } from "../util.js";

const DIFFICULTIES = [
  ["Facile", "easy", "btn-green"],
  ["Moyen", "medium", "btn-blue"],
  ["Difficile", "hard", "btn-danger"],
];

export default function mountAiDifficulty(root) {
  const back = () => go(homeOrLogin());
  const onKey = (e) => { if (e.key === "Escape") back(); };
  document.addEventListener("keydown", onKey);

  root.append(
    h("header", { class: "page-header" },
      h("button", { class: "btn btn-dim small", text: "← Retour", onclick: back })),
    h("div", { class: "ai-pick" },
      h("h2", { text: "Jouer contre l'IA" }),
      h("p", { class: "dim", text: "Choisissez la difficulté" }),
      h("p", { class: "dimmer", text: "Sans impact sur l'Elo" }),
      DIFFICULTIES.map(([label, difficulty, cls]) =>
        h("button", { class: `btn big ${cls}`, text: label, onclick: () => go("ai_game", { difficulty }) }))),
  );

  return () => document.removeEventListener("keydown", onKey);
}
