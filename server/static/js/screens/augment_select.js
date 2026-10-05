// Rumble: augment selection between rounds (3 proposals, one reroll each, one pick).

import { app, go } from "../app.js";
import { emit, onMany } from "../socket.js";
import { MODIFIER_CODES, h, keyLabel } from "../util.js";

function scorePips(score) {
  return h("span", { class: "pips" }, [0, 1, 2].map((i) => h("span", { class: `pip ${i < score ? `on on-${i}` : ""}` })));
}

export default function mountAugmentSelect(root, { data }) {
  const state = {
    round: 1,
    color: "white",
    proposals: [],
    scores: { white: 0, black: 0 },
    mine: [],
    theirs: [],
    skipped: false,
    rerollUsed: [],
    selected: null,
    confirmed: false,
    keybindIndex: null, // proposal waiting for a key
  };

  const stage = h("div", { class: "aug-stage" });
  const sidebarMine = h("aside", { class: "aug-side left" });
  const sidebarTheirs = h("aside", { class: "aug-side right" });
  const header = h("div", { class: "aug-header" });
  const footer = h("div", { class: "aug-footer" });
  const modal = h("div", { class: "overlay", hidden: true });

  function setup(d) {
    state.round = d.round ?? 1;
    state.color = d.your_color || state.color;
    state.proposals = d.proposals || [];
    state.scores = d.scores || { white: 0, black: 0 };
    state.mine = d.my_augments || [];
    state.theirs = d.opponent_augments || [];
    state.skipped = !!d.skipped;
    state.rerollUsed = state.proposals.map(() => false);
    state.selected = null;
    state.confirmed = false;
    state.keybindIndex = null;
    // A new match starts at round 1: forget the previous match's key assignments.
    if (state.round === 1) app.keybinds = {};
    render();
  }

  function render() {
    const foe = state.color === "white" ? "black" : "white";
    header.replaceChildren(
      h("h2", { text: `RUMBLE — Manche ${state.round}` }),
      h("p", { class: "dim", text: "Choisissez votre augment pour cette manche" }),
      h("div", { class: "aug-score" },
        h("div", {}, h("span", { class: "who", text: "Vous" }), scorePips(state.scores[state.color] || 0)),
        h("div", {}, h("span", { class: "who", text: "Adv." }), scorePips(state.scores[foe] || 0))),
    );

    stage.replaceChildren();
    if (state.skipped) {
      stage.append(h("div", { class: "aug-skipped" },
        h("h3", { text: "L'adversaire a utilisé Aura Farming" }),
        h("p", { text: "Vous ne recevez pas d'augment ce tour." }),
        h("p", { class: "dim", text: "En attente de l'adversaire..." })));
    } else {
      state.proposals.forEach((aug, i) => stage.append(card(aug, i)));
    }

    footer.textContent = state.confirmed && !state.skipped
      ? "✓  Augment sélectionné — En attente de l'adversaire..." : "";

    sidebarMine.replaceChildren(h("h4", { text: "Vos augments" }), augList(state.mine));
    sidebarTheirs.replaceChildren(h("h4", { text: "Adversaire" }), augList(state.theirs));
    renderModal();
  }

  const augList = (list) => h("ul", {}, list.map((a) =>
    h("li", { class: a.is_activable ? "activable" : "", text: `• ${a.name}` })));

  function card(aug, i) {
    const activable = !!aug.is_activable;
    const used = state.rerollUsed[i];
    const selected = state.selected === i;
    const reroll = h("button", {
      class: `reroll ${used ? "used" : ""}`, type: "button",
      title: used ? "Reroll déjà utilisé" : "Relancer cet augment",
      "aria-label": "Relancer cet augment",
      text: used ? "✓" : "↺",
      onclick: (e) => { e.stopPropagation(); if (!used) emit("rumble:reroll", { index: i }); },
    });
    return h("div", {
      class: `aug-card ${activable ? "is-act" : "is-pass"} ${selected ? "selected" : ""} ${state.confirmed ? "locked" : ""}`,
      role: "button", tabindex: state.confirmed ? "-1" : "0",
      onclick: () => clickCard(i),
      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); clickCard(i); } },
    },
    h("div", { class: "strip" }),
    h("div", { class: "kind", text: activable ? "ACTIVABLE" : "PASSIF" }),
    h("div", { class: "name", text: aug.name || "???" }),
    h("div", { class: "rule" }),
    h("p", { class: "desc", text: aug.description || "" }),
    activable ? h("div", { class: "cd-badge", text: `Cooldown : ${Math.round(aug.cooldown || 0)}s` }) : null,
    h("div", { class: "hint", text: activable ? "Clic → assigner une touche" : "Clic → choisir cet augment" }),
    state.confirmed || selected ? null : reroll);
  }

  function clickCard(i) {
    if (state.confirmed || state.keybindIndex !== null) return;
    const aug = state.proposals[i];
    if (!aug) return;
    if (aug.is_activable) {
      state.keybindIndex = i;
      renderModal();
    } else {
      confirmSelect(i, null);
    }
  }

  function confirmSelect(i, keybind) {
    const aug = state.proposals[i];
    state.selected = i;
    state.confirmed = true;
    state.keybindIndex = null;
    if (keybind) app.keybinds[aug.id] = keybind;
    emit("rumble:select_augment", { augment_id: aug.id });
    render();
  }

  function renderModal() {
    const i = state.keybindIndex;
    if (i === null || !state.proposals[i]) {
      modal.hidden = true;
      return;
    }
    modal.hidden = false;
    modal.replaceChildren(h("div", { class: "modal center keybind" },
      h("h3", { text: "Assigner une touche" }),
      h("p", { class: "dim", text: state.proposals[i].name }),
      h("p", { class: "prompt", text: "Appuyez sur une touche..." }),
      h("p", { class: "dim small", id: "keybind-error" }),
      h("p", { class: "dim small", text: "Échap pour annuler" })));
  }

  function onKey(e) {
    if (e.key === "Escape") {
      if (state.keybindIndex !== null) { state.keybindIndex = null; renderModal(); }
      else leave();
      return;
    }
    if (state.keybindIndex === null || MODIFIER_CODES.has(e.code) || e.repeat) return;
    e.preventDefault();
    // One key = one augment: refuse a key already used by another activable augment.
    const taken = Object.entries(app.keybinds).find(([id, k]) => k.code === e.code
      && state.mine.some((a) => a.id === id));
    if (taken) {
      const err = modal.querySelector("#keybind-error");
      if (err) err.textContent = "Cette touche est déjà utilisée par un autre augment";
      return;
    }
    confirmSelect(state.keybindIndex, { code: e.code, label: keyLabel(e) });
  }

  function leave() {
    emit("rumble:leave_room");
    go("home");
  }

  const off = onMany({
    "rumble:augment_phase": (d) => setup(d),
    "rumble:rerolled": (d) => {
      const i = d.index;
      if (i >= 0 && i < state.proposals.length && d.augment) {
        state.proposals[i] = d.augment;
        if (!d.infinite) state.rerollUsed[i] = true;
        render();
      }
    },
    "rumble:round_start": (d) => go("rumble_game", { data: d }),
  });
  document.addEventListener("keydown", onKey);

  root.append(
    h("div", { class: "aug-screen" },
      h("button", { class: "btn btn-danger small aug-back", text: "← Quitter", onclick: leave }),
      header, stage, footer, sidebarMine, sidebarTheirs),
    modal,
  );
  setup(data);

  return () => {
    off();
    document.removeEventListener("keydown", onKey);
  };
}
