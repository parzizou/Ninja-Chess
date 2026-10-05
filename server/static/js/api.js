// REST client + session persistence ("rester connecté").

const STORAGE_KEY = "ninja_chess_session";

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export const session = {
  token: null,
  username: null,

  /** Restore a saved session (localStorage = stay logged in, sessionStorage = this tab only). */
  load() {
    for (const store of [localStorage, sessionStorage]) {
      try {
        const data = JSON.parse(store.getItem(STORAGE_KEY) || "null");
        if (data && data.token && data.username) {
          this.token = data.token;
          this.username = data.username;
          return data;
        }
      } catch { /* storage unavailable or corrupt */ }
    }
    return null;
  },

  save(username, token, persist) {
    this.token = token;
    this.username = username;
    this.clearStorage();
    try {
      (persist ? localStorage : sessionStorage).setItem(STORAGE_KEY, JSON.stringify({ username, token }));
    } catch { /* ignore */ }
  },

  clearStorage() {
    for (const store of [localStorage, sessionStorage]) {
      try { store.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    }
  },

  clear() {
    this.token = null;
    this.username = null;
    this.clearStorage();
  },
};

async function request(method, path, { json, form } = {}) {
  const headers = {};
  let body;
  if (session.token) headers.Authorization = `Bearer ${session.token}`;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }
  let res;
  try {
    res = await fetch(path, { method, headers, body });
  } catch {
    throw new ApiError(0, "network");
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new ApiError(res.status, data && data.detail);
  return data;
}

export const api = {
  register: (username, password) => request("POST", "/auth/register", { json: { username, password } }),
  login: (username, password) => request("POST", "/auth/login", { json: { username, password } }),
  me: () => request("GET", "/auth/me"),
  leaderboard: () => request("GET", "/leaderboard"),
  profile: (username) => request("GET", `/users/${encodeURIComponent(username)}/profile`),
  history: (username) => request("GET", `/users/${encodeURIComponent(username)}/history`),
  uploadAvatar(file) {
    const form = new FormData();
    form.append("file", file, file.name);
    return request("POST", "/users/avatar", { form });
  },
};
