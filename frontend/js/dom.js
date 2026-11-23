// Tiny DOM toolkit. All text goes through textContent, never innerHTML, so
// user content can't inject markup.

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * h("button.btn.btn-primary", { onclick, type: "button" }, "Save")
 * Tag shorthand supports .class and #id. Children may be strings, nodes,
 * arrays, null/false (skipped).
 */
export function h(tag, attrs, ...children) {
  if (attrs == null || typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs)) {
    children.unshift(attrs);
    attrs = {};
  }
  const [, name = "div", rest = ""] = tag.match(/^([a-z0-9-]*)(.*)$/i);
  const el = document.createElement(name || "div");
  for (const part of rest.match(/[.#][^.#]+/g) || []) {
    if (part[0] === ".") el.classList.add(part.slice(1));
    else el.id = part.slice(1);
  }
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

function setAttrs(el, attrs) {
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.classList.add(...String(v).split(/\s+/).filter(Boolean));
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "style") for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
    else if (k === "ref") v(el);
    else if (k === "value") el.value = v;
    else if (k in el && typeof v !== "string" && k !== "list") el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
}

/** Like Element.append, but skips null/false/undefined (native append prints them). */
export function append(el, ...children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

/** Mark children for the one orchestrated entrance per view. */
export function reveal(...els) {
  els.flat().forEach((el, i) => {
    if (!el) return;
    el.classList.add("reveal");
    el.style.setProperty("--i", String(Math.min(i, 8)));
  });
}

/**
 * Autofocus after the router has settled, but never steal focus from a field
 * the user (or a password manager) is already typing into. Skipped on touch
 * devices, where focusing would pop the keyboard over the page uninvited.
 */
export function autofocus(el) {
  if (window.matchMedia("(pointer: coarse)").matches) return;
  setTimeout(() => {
    const active = document.activeElement;
    if (active && active !== document.body && active.id !== "main") return;
    el.focus();
  }, 50);
}

// --------------------------------------------------------------- icons

const ICONS = {
  home: "M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z",
  gift: "M4 11h16v9H4zM3 7h18v4H3zM12 7v13M12 7S10.5 3 8 3.5 7 7 12 7zm0 0s1.5-4 4-3.5S17 7 12 7z",
  ribbon: "M5 6h14v13H5zM12 6v13M5 12h14M9 3l3 3 3-3",
  check: "m5 12.5 4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6 6 18",
  plus: "M12 5v14M5 12h14",
  back: "M15 5l-7 7 7 7",
  chevron: "m9 5 7 7-7 7",
  down: "m6 9 6 6 6-6",
  up: "m6 15 6-6 6 6",
  pencil: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  trash: "M5 7h14M10 7V4h4v3m-7 0 1 13h8l1-13",
  copy: "M9 9h10v11H9zM5 15V4h10",
  link: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
  truck: "M3 6h11v10H3zM14 10h4l3 3v3h-7M7.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM17.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  pin: "M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  store: "M4 9h16l-1-5H5zM5 9v11h14V9M10 20v-6h4v6",
  flag: "M5 21V4m0 0h11l-2 4 2 4H5",
  user: "M19 20v-1a5 5 0 0 0-5-5h-4a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  users: "M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 10.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21 19v-1a4 4 0 0 0-3-3.9M15.5 3.6a3.5 3.5 0 0 1 0 6.8",
  shield: "M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z",
  logout: "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10",
  alert: "M12 8v5m0 3.5v.01M10.3 3.9 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  retry: "M4 12a8 8 0 1 0 2.4-5.7M4 4v4.5h4.5",
  printer: "M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z",
  share: "M12 3v12M8 7l4-4 4 4M5 12v7a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7",
  archive: "M3 4h18v4H3zM5 8v12h14V8M10 12h4",
  note: "M5 4h14v16H5zM8 9h8M8 13h8M8 17h5",
};

export function icon(name, label) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.classList.add("icon");
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else {
    svg.setAttribute("aria-hidden", "true");
  }
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICONS[name] || "");
  svg.append(path);
  return svg;
}

// --------------------------------------------------------------- feedback

/** Toast with an optional action button (e.g. Undo). */
export function toast(message, kind = "ok", { ms = 4200, action } = {}) {
  // Modal dialogs live in the top layer, above the page's toast area; show toasts inside the open one.
  const dialogs = document.querySelectorAll("dialog[open]");
  const top = dialogs[dialogs.length - 1];
  let host = document.getElementById("toasts");
  if (top) {
    host = top.querySelector(":scope > .toasts") || top.appendChild(h("div.toasts", { role: "status", "aria-live": "polite" }));
  }
  const el = h(`div.toast.toast-${kind}`, icon(kind === "error" ? "alert" : "check"), h("span", message));
  let timer;
  const dismiss = () => {
    clearTimeout(timer);
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 220);
  };
  if (action) {
    el.append(h("button.toast-action", { type: "button", onclick: () => { dismiss(); action.run(); } }, action.label));
  }
  host.append(el);
  timer = setTimeout(dismiss, action ? Math.max(ms, 6000) : ms);
  return dismiss;
}

export function formError(message) {
  return h("div.form-error", { role: "alert" }, icon("alert"), h("span", message));
}

export function spinner() {
  return h("span.spinner", { "aria-hidden": "true" });
}

/** Disable a button and show a spinner while an async action runs. */
export async function busy(button, fn) {
  const prev = Array.from(button.childNodes);
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  clear(button).append(spinner(), h("span", button.dataset.busyLabel || "Saving…"));
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    clear(button).append(...prev);
  }
}

export function skeletonLines(widths = ["w-70", "w-100", "w-85", "w-40"]) {
  return widths.map((w) => h(`span.skeleton.skeleton-line.${w}`));
}

/** Centred modal dialog returning a promise of the chosen action's value. */
export function dialog({ title, body, actions }) {
  return new Promise((resolve) => {
    const dlg = h("dialog.dialog", { "aria-labelledby": "dlg-title" });
    const close = (value) => {
      dlg.close();
      dlg.remove();
      resolve(value);
    };
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); close(null); });
    const buttons = actions.map((a) =>
      h(`button.btn${a.primary ? ".btn-primary" : ""}${a.danger ? ".btn-danger" : ""}`, {
        type: "button",
        onclick: () => close(a.value),
      }, a.label),
    );
    dlg.append(h("div.dialog-body", h("h2#dlg-title", title), body, h("div.dialog-actions", buttons)));
    document.body.append(dlg);
    dlg.showModal();
  });
}

export function confirmDialog(title, message, confirmLabel = "Delete", { danger = true } = {}) {
  return dialog({
    title,
    body: h("p.muted", message),
    actions: [
      { label: "Cancel", value: false },
      { label: confirmLabel, value: true, primary: !danger, danger },
    ],
  });
}

/** Clipboard with a fallback for plain-HTTP origins, where navigator.clipboard is unavailable. */
export async function copyText(text, what = "Copied") {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = h("textarea", { readonly: true, style: { position: "fixed", top: "0", opacity: "0" } });
      ta.value = text;
      document.body.append(ta);
      ta.select();
      ta.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      ta.remove();
      if (!ok) throw new Error("copy failed");
    }
    toast(what);
  } catch {
    toast("Couldn't copy: press and hold the text to copy it", "error");
  }
}

/** Segmented control (radio group) that works with one thumb. */
export function segmented(name, options, value, { label, onchange } = {}) {
  const group = h("div.segmented", { role: "radiogroup", "aria-label": label || name });
  for (const opt of options) {
    const id = `${name}-${opt.value}`;
    const input = h("input", { type: "radio", name, id, value: String(opt.value), checked: String(opt.value) === String(value) });
    if (onchange) input.addEventListener("change", () => onchange(opt.value));
    group.append(h(`label.seg${opt.className ? `.${opt.className}` : ""}`, { for: id }, input, opt.dot && h("span.dot"), h("span", opt.label)));
  }
  return group;
}

export function radioValue(form, name) {
  return form.querySelector(`input[name="${name}"]:checked`)?.value ?? null;
}
