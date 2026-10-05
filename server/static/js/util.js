// Small DOM helpers. Everything user-controlled (usernames, room names…) goes
// through textContent / text nodes, never innerHTML.

export const now = () => Date.now() / 1000;

export function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style" && typeof value === "object") {
      for (const [prop, val] of Object.entries(value)) {
        if (prop.startsWith("--")) node.style.setProperty(prop, val);
        else node.style[prop] = val;
      }
    }
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function toast(message, kind = "info", ms = 3500) {
  const host = document.getElementById("toasts");
  if (!host) return;
  const node = h("div", { class: `toast toast-${kind}`, text: message });
  host.append(node);
  setTimeout(() => node.classList.add("toast-out"), ms);
  setTimeout(() => node.remove(), ms + 400);
}

/** Runs `fn(dt)` every animation frame until the returned function is called. */
export function startLoop(fn) {
  let id = 0;
  let last = performance.now();
  let stopped = false;
  const frame = (t) => {
    if (stopped) return;
    const dt = Math.min(0.1, (t - last) / 1000);
    last = t;
    fn(dt);
    id = requestAnimationFrame(frame);
  };
  id = requestAnimationFrame(frame);
  return () => {
    stopped = true;
    cancelAnimationFrame(id);
  };
}

/** Collects teardown callbacks so a screen can clean up in one call. */
export class Disposer {
  constructor() { this.fns = []; }
  add(fn) { this.fns.push(fn); return fn; }
  listen(target, type, handler, options) {
    target.addEventListener(type, handler, options);
    this.fns.push(() => target.removeEventListener(type, handler, options));
  }
  run() {
    for (const fn of this.fns.splice(0)) {
      try { fn(); } catch (e) { console.error(e); }
    }
  }
}

const KEY_NAMES = { Space: "Esp", Enter: "Entr", Tab: "Tab", ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→" };
export const MODIFIER_CODES = new Set([
  "ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight",
  "MetaLeft", "MetaRight", "CapsLock", "ContextMenu",
]);

/** Human readable label for a keyboard event (what is printed on the pressed key). */
export function keyLabel(event) {
  const { code, key } = event;
  if (/^(Digit|Numpad)\d$/.test(code)) return code.slice(-1);
  if (KEY_NAMES[code]) return KEY_NAMES[code];
  if (/^F\d{1,2}$/.test(code)) return code;
  if (key && key.length === 1) return key.toUpperCase();
  return key || code;
}
