// Shown after creating a room, until a second player joins.

import { app, go } from "../app.js";
import { emit, onMany } from "../socket.js";
import { h } from "../util.js";

export default function mountWaiting(root, { room, mode }) {
  const rumble = mode === "rumble";

  function cancel() {
    emit(rumble ? "rumble:leave_room" : "room:leave");
    go(rumble ? "rumble_rooms" : "rooms");
  }

  const off = onMany(rumble
    ? { "rumble:augment_phase": (data) => go("augment_select", { data }) }
    : { "room:ready": (data) => go("game", { init: data }) });

  const onKey = (e) => { if (e.key === "Escape") cancel(); };
  document.addEventListener("keydown", onKey);

  const elo = rumble ? app.user.elo_rumble : app.user.elo_standard;
  root.append(
    h("div", { class: "waiting" },
      h("h2", { text: "En attente d'un adversaire" }),
      h("p", { class: "dim", text: `Room : ${room.name || "Room"}` }),
      h("p", { class: "player-line", text: `${app.user.username}  •  Elo ${elo}` }),
      h("div", { class: "spinner", "aria-hidden": "true" }, Array.from({ length: 10 }, (_, i) =>
        h("span", { style: { "--i": i } }))),
      h("button", { class: "btn btn-danger", text: "Annuler", onclick: cancel }),
    ),
  );

  return () => {
    off();
    document.removeEventListener("keydown", onKey);
  };
}
