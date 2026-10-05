import { api } from "../api.js";
import { app, go } from "../app.js";
import { h } from "../util.js";

const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

export default function mountProfile(root) {
  let alive = true;
  const body = h("div", { class: "profile-body" }, h("p", { class: "dim center", text: "Chargement..." }));
  const status = h("div", { class: "avatar-status dim", role: "status" });
  const fileInput = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp", hidden: true });
  const avatar = h("img", { class: "avatar", alt: "Avatar", width: "96", height: "96", src: "/assets/default_avatar.png" });

  function setAvatar(url) {
    avatar.src = url || "/assets/default_avatar.png";
  }

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    fileInput.value = "";
    if (!file) return;
    if (file.size > MAX_AVATAR_BYTES) { status.textContent = "Image trop lourde (max 2 Mo)"; return; }
    status.textContent = "Envoi en cours...";
    try {
      const res = await api.uploadAvatar(file);
      if (!alive) return;
      setAvatar(res.avatar_url);
      status.textContent = "Avatar mis à jour";
    } catch {
      if (alive) status.textContent = "Échec de l'envoi";
    }
  });

  Promise.all([api.profile(app.user.username), api.history(app.user.username)]).then(([p, history]) => {
    if (!alive) return;
    app.user.elo_standard = p.elo_standard;
    app.user.elo_rumble = p.elo_rumble;
    setAvatar(p.avatar_url);

    const stats = [
      ["Joueur", p.username],
      ["Elo Standard", p.elo_standard],
      ["Elo Rumble", p.elo_rumble],
      ["Parties jouées", p.games_played],
      ["Victoires", p.games_won],
      ["Défaites", p.games_lost],
    ];
    body.replaceChildren(
      h("div", { class: "avatar-block" },
        avatar,
        h("button", { class: "btn btn-primary small", text: "Changer l'avatar", onclick: () => fileInput.click() }),
        status, fileInput),
      h("dl", { class: "stats" }, stats.map(([label, value]) => [h("dt", { text: label }), h("dd", { text: value })])),
      h("h3", { text: "Dernières parties" }),
      history.length
        ? h("ul", { class: "history" }, history.slice(0, 10).map((g) => {
          const win = g.result === "win";
          return h("li", { class: win ? "win" : "loss" },
            h("span", { class: "res", text: win ? "V" : "D" }),
            h("span", { class: "opp", text: `vs ${g.opponent}` }),
            h("span", { class: "elo", text: g.elo_change >= 0 ? `+${g.elo_change}` : String(g.elo_change) }),
            h("span", { class: "mode", text: g.mode }));
        }))
        : h("p", { class: "dim center", text: "Aucune partie jouée" }),
    );
  }).catch(() => {
    if (alive) body.replaceChildren(h("p", { class: "error center", text: "Impossible de charger le profil" }));
  });

  const back = () => go("home");
  const onKey = (e) => { if (e.key === "Escape") back(); };
  document.addEventListener("keydown", onKey);

  root.append(
    h("header", { class: "page-header" },
      h("button", { class: "btn btn-dim small", text: "← Retour", onclick: back }),
      h("h2", { text: "Mon Profil" })),
    body,
  );

  return () => {
    alive = false;
    document.removeEventListener("keydown", onKey);
  };
}
