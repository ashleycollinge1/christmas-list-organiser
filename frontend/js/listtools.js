// Search boxes and multi-select, shared by the wish list, person, occasion and People pages.

import { h, icon } from "./dom.js";

const norm = (s) => String(s ?? "").toLocaleLowerCase("en-GB").normalize("NFKD").replace(/[̀-ͯ]/g, "");

/** True when every word of the query appears somewhere in the given fields. */
export function matches(query, ...fields) {
  const words = norm(query).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = norm(fields.filter(Boolean).join(" "));
  return words.every((w) => hay.includes(w));
}

/**
 * Search input that keeps its value and focus across redraws.
 * state: { query } object owned by the view; onInput() redraws.
 */
export function searchBox(state, { placeholder = "Search", label = "Search", onInput }) {
  const input = h("input.input", {
    type: "search", value: state.query, placeholder, "aria-label": label,
    autocomplete: "off", autocapitalize: "none", autocorrect: "off", spellcheck: "false", enterkeyhint: "search",
  });
  const clearBtn = h("button.search-clear", {
    type: "button", "aria-label": "Clear search", hidden: !state.query,
    onclick: () => { state.query = ""; onInput(); },
  }, icon("x"));
  input.addEventListener("input", () => {
    state.query = input.value;
    state.refocus = true;
    onInput();
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.query) { state.query = ""; onInput(); } });
  const box = h("div.search", { role: "search" }, icon("search"), input, clearBtn);
  if (state.refocus) {
    // Typing redraws the list; put the caret back where it was.
    state.refocus = false;
    queueMicrotask(() => { input.focus({ preventScroll: true }); input.setSelectionRange(input.value.length, input.value.length); });
  }
  return box;
}

/** "3 of 12 match" line, or a "nothing found" message. */
export function searchSummary(state, shown, total, noun = "item", plural = `${noun}s`) {
  if (!state.query.trim()) return null;
  if (!shown) return h("p.search-empty", `No ${plural} match “${state.query.trim()}”.`);
  return h("p.search-count", `${shown} of ${total} ${total === 1 ? noun : plural} match`);
}

/**
 * Selection state for a view. `sel.active` toggles the mode, `sel.ids` holds the chosen ids.
 */
export function createSelection() {
  return { active: false, ids: new Set() };
}

/** A tickable row used in selection mode (the normal row's buttons are replaced by one big target). */
export function selectRow(sel, id, content, { className = "", onChange }) {
  const checked = sel.ids.has(id);
  const input = h("input", {
    type: "checkbox", checked,
    onchange: (e) => { if (e.target.checked) sel.ids.add(id); else sel.ids.delete(id); onChange(); },
  });
  return h(`li.selectable${className ? `.${className}` : ""}${checked ? ".is-selected" : ""}`,
    h("label.select-box", input, h("span.check-box", { "aria-hidden": "true" }, icon("check")), h("span.sr-only", "Select")),
    h("div.select-content", { onclick: () => { input.checked = !input.checked; input.dispatchEvent(new Event("change")); } }, content));
}

/** "Select" / "Cancel" toggle for the top of a list. */
export function selectToggle(sel, { disabled = false, onChange }) {
  return h(`button.btn.btn-sm${sel.active ? ".btn-primary" : ""}`, {
    type: "button", disabled,
    onclick: () => { sel.active = !sel.active; sel.ids.clear(); onChange(); },
  }, sel.active ? "Cancel" : "Select");
}

/**
 * Floating action bar while selecting.
 * visibleIds: ids currently shown (Select all picks these). actions: [{ label, danger, run(ids) }].
 */
export function selectBar(sel, visibleIds, actions, { onChange }) {
  const n = sel.ids.size;
  const allOn = visibleIds.length > 0 && visibleIds.every((id) => sel.ids.has(id));
  return h("div.select-bar", { role: "toolbar", "aria-label": "Selected items" },
    h("div.select-bar-inner",
      h("div.select-bar-top",
        h("span", { "aria-live": "polite" }, n ? `${n} selected` : "Tick items to select"),
        h("button.btn.btn-sm.btn-link", {
          type: "button",
          onclick: () => { if (allOn) visibleIds.forEach((id) => sel.ids.delete(id)); else visibleIds.forEach((id) => sel.ids.add(id)); onChange(); },
        }, allOn ? "Select none" : "Select all")),
      h("div.select-bar-actions", actions.map((a) =>
        h(`button.btn${a.danger ? ".btn-danger-ghost" : ""}`, { type: "button", disabled: !n, onclick: () => a.run([...sel.ids]) }, a.label)))));
}
