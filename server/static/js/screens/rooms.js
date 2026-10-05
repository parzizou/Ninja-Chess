// Room browser (create / join), shared by the Standard and Rumble modes.

import { app, go } from "../app.js";
import { emit, onMany } from "../socket.js";
import { h, toast } from "../util.js";

const MODES = {
  standard: {
    title: "Rooms disponibles",
    empty: "Aucune room disponible — créez-en une !",
    defaultName: (u) => `Room de ${u}`,
    cls: "mode-standard",
    events: { list: "room:list", created: "room:created", error: "room:error", ready: "room:ready" },
    out: { create: "room:create", join: "room:join", refresh: "room:refresh" },
  },
  rumble: {
    title: "RUMBLE — Rooms",
    empty: "Aucune room Rumble — créez-en une !",
    defaultName: (u) => `Rumble de ${u}`,
    cls: "mode-rumble",
    events: { list: "rumble:room_list", created: "rumble:room_created", error: "rumble:error", ready: "rumble:augment_phase" },
    out: { create: "rumble:create_room", join: "rumble:join_room", refresh: "rumble:refresh_rooms" },
  },
};

function mountRooms(root, mode) {
  const cfg = MODES[mode];
  let rooms = [];

  const list = h("div", { class: "room-list" });
  const input = h("input", { type: "text", maxlength: "40", placeholder: "Nom de la room", autocomplete: "off" });

  function render() {
    list.replaceChildren();
    if (!rooms.length) {
      list.append(h("p", { class: "empty", text: cfg.empty }));
      return;
    }
    for (const room of rooms) {
      list.append(h("button", {
        class: "room-btn",
        onclick: () => emit(cfg.out.join, { room_id: room.room_id }),
      },
      h("span", { class: "room-name", text: room.name }),
      h("span", { class: "room-meta", text: `${room.creator} · ${room.players}/2` })));
    }
  }

  const create = () => {
    const name = input.value.trim() || cfg.defaultName(app.user.username);
    emit(cfg.out.create, { name });
  };
  const refresh = () => emit(cfg.out.refresh);

  const off = onMany({
    [cfg.events.list]: (data) => { rooms = Array.isArray(data) ? data : []; render(); },
    [cfg.events.created]: (data) => go("waiting", { room: data, mode }),
    [cfg.events.error]: (data) => toast((data && data.message) || "Erreur", "error"),
    [cfg.events.ready]: (data) => (mode === "rumble" ? go("augment_select", { data }) : go("game", { init: data })),
  });

  const onKey = (e) => {
    if (e.key === "Escape") go("home");
    else if (e.key === "Enter" && document.activeElement === input) create();
  };
  document.addEventListener("keydown", onKey);

  root.classList.add(cfg.cls);
  root.append(
    h("header", { class: "page-header" },
      h("button", { class: "btn btn-dim small", text: "← Retour", onclick: () => go("home") }),
      h("h2", { text: cfg.title })),
    h("div", { class: "create-row" },
      input,
      h("button", { class: "btn btn-primary", text: "Créer", onclick: create })),
    list,
    h("div", { class: "footer-row" }, h("button", { class: "btn btn-secondary", text: "Rafraîchir", onclick: refresh })),
  );
  render();
  refresh();

  return () => {
    off();
    document.removeEventListener("keydown", onKey);
  };
}

export const mountStandardRooms = (root) => mountRooms(root, "standard");
export const mountRumbleRooms = (root) => mountRooms(root, "rumble");
