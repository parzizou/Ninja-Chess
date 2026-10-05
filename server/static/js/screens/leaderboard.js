import { api } from "../api.js";
import { app, go, homeOrLogin } from "../app.js";
import { h } from "../util.js";

export default function mountLeaderboard(root) {
  const body = h("div", { class: "lb-body" }, h("p", { class: "dim center", text: "Chargement..." }));
  let alive = true;

  api.leaderboard().then((entries) => {
    if (!alive) return;
    const rows = entries.slice(0, 20).map((e, i) => h("tr", {
      class: `${e.rank <= 3 ? `rank-${e.rank}` : ""} ${app.user && e.username === app.user.username ? "me" : ""}`,
    },
    h("td", { text: e.rank }),
    h("td", { text: e.username }),
    h("td", { text: e.elo_standard }),
    h("td", { text: e.games_played }),
    h("td", { text: e.games_won })));
    body.replaceChildren(rows.length
      ? h("table", { class: "table" },
        h("thead", {}, h("tr", {}, ["#", "Joueur", "Elo", "Parties", "Victoires"].map((t) => h("th", { text: t })))),
        h("tbody", {}, rows))
      : h("p", { class: "dim center", text: "Aucun joueur pour le moment" }));
  }).catch(() => {
    if (alive) body.replaceChildren(h("p", { class: "error center", text: "Impossible de charger le classement" }));
  });

  const back = () => go(homeOrLogin());
  const onKey = (e) => { if (e.key === "Escape") back(); };
  document.addEventListener("keydown", onKey);

  root.append(
    h("header", { class: "page-header" },
      h("button", { class: "btn btn-dim small", text: "← Retour", onclick: back }),
      h("h2", { text: "Classement" })),
    body,
  );

  return () => {
    alive = false;
    document.removeEventListener("keydown", onKey);
  };
}
