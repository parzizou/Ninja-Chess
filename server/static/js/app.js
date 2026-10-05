// Application state + tiny screen router. A screen is a function
// (container, params) => cleanup | void, registered under a name.

import { api, session } from "./api.js";
import * as socket from "./socket.js";
import { toast } from "./util.js";

const root = document.getElementById("app");
const registry = new Map();
let current = null;

export const app = {
  user: null,     // { username, elo_standard, elo_rumble }
  keybinds: {},   // Rumble: augment id -> { code, label }
  currentName: "",
};

export function register(name, mount) { registry.set(name, mount); }

export function go(name, params = {}) {
  const mount = registry.get(name);
  if (!mount) throw new Error(`Unknown screen: ${name}`);
  if (current && current.cleanup) {
    try { current.cleanup(); } catch (e) { console.error(e); }
  }
  const container = document.createElement("div");
  container.className = `screen screen-${name}`;
  root.className = "";
  root.replaceChildren(container);
  app.currentName = name;
  current = { name, cleanup: null };
  const entry = current;
  const cleanup = mount(container, params);
  entry.cleanup = typeof cleanup === "function" ? cleanup : null;
  window.scrollTo(0, 0);
}

export const homeOrLogin = () => (app.user ? "home" : "login");

/** Store the logged-in account and open the realtime connection. */
export function setUser(data) {
  app.user = {
    username: data.username,
    elo_standard: data.elo_standard,
    elo_rumble: data.elo_rumble,
  };
  socket.connect(session.token);
}

export function logout(message) {
  session.clear();
  socket.disconnect();
  app.user = null;
  app.keybinds = {};
  if (message) toast(message, "error");
  go("login");
}

/** Refresh Elo/stats shown in menus (they change after every game). */
export async function refreshUser() {
  if (!app.user) return;
  try {
    const p = await api.profile(app.user.username);
    app.user.elo_standard = p.elo_standard;
    app.user.elo_rumble = p.elo_rumble;
  } catch { /* keep stale values */ }
}
