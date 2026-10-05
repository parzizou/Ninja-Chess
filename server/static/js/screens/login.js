import { api, session } from "../api.js";
import { go, setUser } from "../app.js";
import { h } from "../util.js";

function errorMessage(err, action) {
  if (err.status === 409) return "Ce nom d'utilisateur est déjà pris";
  if (err.status === 401) return "Identifiants incorrects";
  if (err.status === 422) {
    return action === "register"
      ? "Nom d'utilisateur : 3 à 32 caractères, mot de passe : 4 caractères minimum"
      : "Identifiants incorrects";
  }
  return "Erreur de connexion au serveur";
}

export default function mountLogin(root) {
  let busy = false;

  const username = h("input", {
    type: "text", id: "username", name: "username", autocomplete: "username",
    maxlength: "32", placeholder: "Nom d'utilisateur", autofocus: true,
  });
  const password = h("input", {
    type: "password", id: "password", name: "password", autocomplete: "current-password",
    maxlength: "128", placeholder: "Mot de passe",
  });
  const stay = h("input", { type: "checkbox", id: "stay", checked: true });
  stay.checked = true;
  const error = h("div", { class: "form-error", role: "alert" });
  const loginBtn = h("button", { type: "submit", class: "btn btn-primary", text: "Connexion" });
  const registerBtn = h("button", { type: "button", class: "btn btn-secondary", text: "Créer un compte" });

  async function submit(action) {
    if (busy) return;
    const name = username.value.trim();
    const pass = password.value;
    if (!name || !pass) {
      error.textContent = "Veuillez remplir tous les champs";
      return;
    }
    busy = true;
    error.textContent = "";
    loginBtn.disabled = registerBtn.disabled = true;
    loginBtn.textContent = action === "login" ? "Connexion en cours…" : "Connexion";
    try {
      const data = action === "login" ? await api.login(name, pass) : await api.register(name, pass);
      session.save(data.username, data.access_token, stay.checked);
      setUser(data);
      go("home");
    } catch (err) {
      error.textContent = errorMessage(err, action);
      busy = false;
      loginBtn.disabled = registerBtn.disabled = false;
      loginBtn.textContent = "Connexion";
    }
  }

  registerBtn.addEventListener("click", () => submit("register"));

  const form = h("form", { class: "login-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); submit("login"); } },
    h("label", { for: "username", text: "Utilisateur" }), username,
    h("label", { for: "password", text: "Mot de passe" }), password,
    h("div", { class: "row" }, loginBtn, registerBtn),
    h("label", { class: "check", for: "stay" }, stay, " Rester connecté"),
    error,
  );

  root.append(
    h("div", { class: "login-card" },
      h("img", { class: "login-logo", src: "/assets/logo.png", alt: "" }),
      h("h1", { class: "title", text: "NINJA CHESS" }),
      h("p", { class: "subtitle", text: "Échecs en temps réel" }),
      form,
      h("div", { class: "divider", text: "── ou ──" }),
      h("button", { type: "button", class: "btn btn-green wide", text: "Jouer vs IA (sans compte)", onclick: () => go("ai_difficulty") }),
    ),
  );
  username.focus();
}
