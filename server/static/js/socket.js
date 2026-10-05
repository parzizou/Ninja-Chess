// Single Socket.IO connection shared by every screen. Screens subscribe with
// on()/onMany() and must call the returned function when they leave.

import { toast } from "./util.js";

const listeners = new Map(); // event -> Set<fn>
let sock = null;
let onAuthFailure = () => {};

export function setAuthFailureHandler(fn) { onAuthFailure = fn; }

export function connect(token) {
  if (sock) return;
  // `io` comes from the vendored socket.io client script loaded in index.html.
  sock = io({ auth: { token }, transports: ["websocket", "polling"], reconnectionAttempts: 5 });

  sock.onAny((event, data) => {
    const set = listeners.get(event);
    if (set) for (const fn of [...set]) fn(data);
  });
  sock.on("connect_error", (err) => {
    // The server refuses the handshake with these messages when the token is no longer valid.
    if (["Invalid token", "User not found", "No token provided"].includes(err.message)) {
      onAuthFailure();
    }
  });
  sock.io.on("reconnect_failed", () => toast("Connexion au serveur perdue", "error", 6000));
  sock.on("disconnect", (reason) => {
    if (reason === "io server disconnect" || reason === "transport close" || reason === "ping timeout") {
      toast("Connexion au serveur interrompue…", "error");
    }
  });
}

export function disconnect() {
  if (!sock) return;
  sock.disconnect();
  sock = null;
}

export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event)?.delete(fn);
}

/** Subscribe to several events at once: onMany({ "a": fn, "b": fn }) -> unsubscribe all. */
export function onMany(map) {
  const offs = Object.entries(map).map(([event, fn]) => on(event, fn));
  return () => offs.forEach((off) => off());
}

export function emit(event, data) {
  if (!sock) return;
  // socket.io buffers events until the connection is (re)established.
  sock.emit(event, data);
}
