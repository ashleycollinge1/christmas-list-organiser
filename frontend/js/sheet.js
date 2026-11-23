// Bottom sheets tuned for iOS Safari.
//
// - Built on <dialog>.showModal(): native focus trap, Escape, inert page behind.
// - The sheet follows window.visualViewport, so when the keyboard opens it shrinks
//   to the visible area: the header (Cancel / Save) never ends up under the
//   keyboard, and the focused field is scrolled into view inside the sheet.
// - The page behind is locked with the position:fixed technique (iOS ignores
//   overflow:hidden on body) and the scroll position is restored on close.

import { h, icon, confirmDialog, formError } from "./dom.js";

let locks = 0;
let savedY = 0;

function lockScroll() {
  if (locks++ > 0) return;
  savedY = window.scrollY;
  const s = document.body.style;
  s.position = "fixed";
  s.top = `-${savedY}px`;
  s.left = "0";
  s.right = "0";
  s.width = "100%";
}

function unlockScroll() {
  if (--locks > 0) return;
  const s = document.body.style;
  s.position = s.top = s.left = s.right = s.width = "";
  window.scrollTo(0, savedY);
}

function followViewport(el) {
  const vv = window.visualViewport;
  if (!vv) return () => {};
  const fit = () => {
    el.style.setProperty("--vvh", `${vv.height}px`);
    el.style.setProperty("--vvt", `${vv.offsetTop}px`);
  };
  const onResize = () => {
    fit();
    // Keyboard opened or closed: keep the focused field visible within the sheet.
    // Scroll only the sheet body: scrollIntoView would also scroll the sheet itself.
    const active = document.activeElement;
    const body = el.querySelector(".sheet-body");
    if (body && active && body.contains(active) && active.matches("input, textarea, select")) {
      const a = active.getBoundingClientRect();
      const b = body.getBoundingClientRect();
      if (a.top < b.top + 12 || a.bottom > b.bottom - 12) {
        body.scrollBy({ top: a.top - b.top - b.height / 3, behavior: "smooth" });
      }
    }
  };
  fit();
  vv.addEventListener("resize", onResize);
  vv.addEventListener("scroll", fit);
  return () => {
    vv.removeEventListener("resize", onResize);
    vv.removeEventListener("scroll", fit);
  };
}

function snapshot(form) {
  return JSON.stringify(Array.from(new FormData(form).entries()));
}

/**
 * Full-height form sheet.
 * onSave(form) may throw an Error to show its message; resolve to close.
 * Returns { close, form, body }.
 */
export function openSheet({ title, build, onSave, saveLabel = "Save", readOnly = false, onClose }) {
  const id = `sheet-${Math.random().toString(36).slice(2, 8)}`;
  const errorHost = h("div", { "aria-live": "assertive" });
  const form = h("form.sheet-body", { id, novalidate: true, autocomplete: "off" });
  const saveBtn = readOnly
    ? null
    : h("button.sheet-action.sheet-save", { type: "submit", form: id }, saveLabel);
  const cancelBtn = h("button.sheet-action", { type: "button" }, readOnly ? "Done" : "Cancel");
  const dlg = h("dialog.sheet", { "aria-labelledby": `${id}-title` },
    h("header.sheet-head", cancelBtn, h(`h2.sheet-title#${id}-title`, title), saveBtn || h("span.sheet-spacer")),
    form);
  form.append(errorHost);
  build(form, { close: () => close() });

  let initial = "";
  let closing = false;
  const stopFollowing = followViewport(dlg);
  // Belt and braces for older Safari without overflow:clip: never let the panel itself scroll.
  dlg.addEventListener("scroll", () => { if (dlg.scrollTop) dlg.scrollTop = 0; });

  function close() {
    if (closing) return;
    closing = true;
    stopFollowing();
    dlg.classList.add("is-closing");
    const done = () => {
      dlg.close();
      dlg.remove();
      unlockScroll();
      onClose?.();
    };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) done();
    else setTimeout(done, 200);
  }

  async function cancel() {
    if (!readOnly && snapshot(form) !== initial) {
      const ok = await confirmDialog("Discard changes?", "You've edited this but haven't saved.", "Discard");
      if (!ok) return;
    }
    close();
  }

  cancelBtn.addEventListener("click", cancel);
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); cancel(); });
  // Tap on the dimmed backdrop (the dialog element itself, outside the panel).
  dlg.addEventListener("click", (e) => { if (e.target === dlg) cancel(); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!onSave || saveBtn?.disabled) return;
    errorHost.replaceChildren();
    saveBtn.disabled = true;
    saveBtn.setAttribute("aria-busy", "true");
    try {
      await onSave(form);
      close();
    } catch (err) {
      errorHost.replaceChildren(formError(err.message || String(err)));
      form.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      saveBtn.disabled = false;
      saveBtn.removeAttribute("aria-busy");
    }
  });

  lockScroll();
  document.body.append(dlg);
  dlg.showModal();
  // showModal focuses the first control, which would pop the iOS keyboard; park focus on the title.
  dlg.querySelector(".sheet-title").setAttribute("tabindex", "-1");
  dlg.querySelector(".sheet-title").focus({ preventScroll: true });
  initial = snapshot(form);
  return { close, form, dlg };
}

/** iOS-style action sheet: a short list of choices anchored to the bottom. */
export function actionSheet({ title, message, actions }) {
  return new Promise((resolve) => {
    const dlg = h("dialog.action-sheet", { "aria-label": title });
    let done = false;
    const close = (value) => {
      if (done) return;
      done = true;
      dlg.classList.add("is-closing");
      setTimeout(() => {
        dlg.close();
        dlg.remove();
        unlockScroll();
        resolve(value);
      }, 180);
    };
    const list = h("div.action-list",
      h("div.action-head", h("p.action-title", title), message && h("p.action-message", message)),
      actions.map((a) => h(`button.action-item${a.className ? `.${a.className}` : ""}`, {
        type: "button",
        "aria-current": a.current ? "true" : null,
        onclick: () => close(a.value),
      }, a.dot && h("span.dot"), h("span", a.label), a.current && icon("check"))));
    const cancel = h("button.action-item.action-cancel", { type: "button", onclick: () => close(null) }, "Cancel");
    dlg.append(list, cancel);
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); close(null); });
    dlg.addEventListener("click", (e) => { if (e.target === dlg) close(null); });
    lockScroll();
    document.body.append(dlg);
    dlg.showModal();
    cancel.focus({ preventScroll: true });
  });
}

// ---------------------------------------------------------------- form fields

let fieldSeq = 0;

/** Labelled field. `input` is an element or an attrs object for an <input>. */
export function field(label, input, { hint, optional = false, className } = {}) {
  const el = input instanceof Node ? input : h("input.input", input);
  const control = el.matches("input, select, textarea") ? el : el.querySelector("input, select, textarea");
  if (!control.id) control.id = `f${++fieldSeq}`;
  const hintEl = hint && h(`p.hint#${control.id}-hint`, hint);
  if (hintEl) control.setAttribute("aria-describedby", hintEl.id);
  return h(`div.field${className ? `.${className}` : ""}`,
    h("label", { for: control.id }, label, optional && h("span.optional", "optional")),
    el,
    hintEl);
}

export function moneyInputEl(name, value, attrs = {}) {
  return h("div.input-money",
    h("span.currency", { "aria-hidden": "true" }, "£"),
    h("input.input", {
      name,
      value,
      inputmode: "decimal",
      enterkeyhint: "next",
      placeholder: "0.00",
      autocomplete: "off",
      ...attrs,
    }));
}
