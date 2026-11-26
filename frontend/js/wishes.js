// Your own wish list: sheet, rows, sharing and the occasion-page card.

import { api } from "./api.js";
import { h, icon, toast, confirmDialog, segmented, radioValue, copyText, dialog } from "./dom.js";
import { openSheet, field, moneyInputEl } from "./sheet.js";
import { money, parseMoney, moneyInput } from "./format.js";
import { linkChip } from "./components.js";

export const WISH_PRIORITIES = [
  { value: 1, label: "Really want" },
  { value: 2, label: "Would like" },
  { value: 3, label: "Nice to have" },
];
const PRIORITY = Object.fromEntries(WISH_PRIORITIES.map((p) => [p.value, p.label]));

export function wishPrice(w) {
  if (w.price_pence == null) return null;
  return w.quantity > 1 ? `${w.quantity} × ${money(w.price_pence)}` : money(w.price_pence);
}

export function summaryText(t) {
  if (!t.count) return "Nothing listed";
  const parts = [`${t.count} ${t.count === 1 ? "wish" : "wishes"}`, money(t.total_pence)];
  if (t.unpriced) parts.push(`${t.unpriced} without a price`);
  return parts.join(" · ");
}

/** Read your fields from a wish form (shared by the sheet and the share form). */
export function readWish(form) {
  const description = form.description.value.trim();
  if (!description) throw new Error("Say what you'd like.");
  const price = parseMoney(form.price.value);
  if (Number.isNaN(price)) throw new Error("Price should be an amount like 24.99.");
  const qty = Number(form.quantity.value || 1);
  if (!Number.isInteger(qty) || qty < 1 || qty > 99) throw new Error("Quantity should be between 1 and 99.");
  return {
    description,
    price_pence: price,
    quantity: qty,
    link: form.link.value.trim() || null,
    priority: Number(radioValue(form, "priority")),
    notes: form.notes.value,
    occasion_id: form.occasion_id.value ? Number(form.occasion_id.value) : null,
  };
}

/** The editable fields, used by the sheet and the share form. */
export function wishFields(w, occasions) {
  const current = w.occasion;
  const options = occasions.filter((o) => !o.is_archived || o.id === current?.id);
  return [
    field("What would you like?", h("textarea.input.input-title", {
      name: "description", rows: 2, required: true, maxlength: 200, enterkeyhint: "next",
      placeholder: "e.g. Noise-cancelling headphones", value: w.description ?? "",
    })),
    h("div.field-row",
      field("Price", moneyInputEl("price", moneyInput(w.price_pence)), { optional: true }),
      field("Qty", h("input.input", { name: "quantity", value: w.quantity ?? 1, inputmode: "numeric", pattern: "[0-9]*", maxlength: 2, autocomplete: "off" }), { className: "field-qty" })),
    field("Link", h("input.input", { name: "link", type: "url", inputmode: "url", value: w.link ?? "", autocapitalize: "none", autocorrect: "off", spellcheck: "false", autocomplete: "off", placeholder: "https://" }), { optional: true }),
    h("div.field", h("span.label", "How much do you want it?"), segmented("priority", WISH_PRIORITIES, w.priority ?? 2, { label: "Priority" })),
    field("List", h("select.input", { name: "occasion_id" },
      h("option", { value: "" }, "Anytime"),
      options.map((o) => h("option", { value: String(o.id), selected: current?.id === o.id }, o.is_archived ? `${o.name} (archived)` : o.name))), {
      hint: "Anytime ideas can be moved to an occasion later.",
    }),
    field("Notes", h("textarea.input", { name: "notes", rows: 3, maxlength: 4000, value: w.notes ?? "", placeholder: "Size, colour, “the blue one”…" }), { optional: true }),
  ];
}

let occasionsCache = null;
export async function occasionChoices({ fresh = false } = {}) {
  if (!occasionsCache || fresh) occasionsCache = (await api("/api/occasions")).occasions;
  return occasionsCache;
}

/** Add or edit a wish. `occasionId` preselects the list for a new one. */
export async function openWishSheet({ wish, occasionId = null, onSaved }) {
  const occasions = await occasionChoices({ fresh: true });
  const w = wish || { priority: 2, quantity: 1, occasion: occasions.find((o) => o.id === occasionId) || null };
  return openSheet({
    title: wish ? "Edit wish" : "Add a wish",
    saveLabel: wish ? "Save" : "Add",
    build(form, { close }) {
      form.append(...wishFields(w, occasions));
      if (!wish) return;
      form.append(h("div.stack.sheet-actions",
        h("button.btn.btn-block", {
          type: "button",
          onclick: async () => {
            try {
              await api(`/api/wishes/${wish.id}`, { method: "PATCH", body: { archived: !wish.archived } });
              toast(wish.archived ? "Restored to your list" : "Archived. Find it under Archived ideas.");
              close();
              onSaved?.();
            } catch (err) {
              toast(err.message, "error");
            }
          },
        }, icon("archive"), wish.archived ? "Restore to my list" : "Archive idea"),
        h("button.btn.btn-danger-ghost.btn-block", {
          type: "button",
          onclick: async () => {
            if (!(await confirmDialog("Delete this wish?", `"${wish.description}" will be removed for good. Archive keeps it as an idea.`))) return;
            try {
              await api(`/api/wishes/${wish.id}`, { method: "DELETE" });
              toast("Wish deleted");
              close();
              onSaved?.();
            } catch (err) {
              toast(err.message, "error");
            }
          },
        }, icon("trash"), "Delete")));
    },
    async onSave(form) {
      const body = readWish(form);
      if (wish) await api(`/api/wishes/${wish.id}`, { method: "PATCH", body });
      else await api("/api/wishes", { method: "POST", body });
      toast(wish ? "Saved" : "Added to your wish list");
      onSaved?.();
    },
  });
}

export function wishRow(w, onSaved) {
  return h(`li.wish${w.archived ? ".is-archived" : ""}`,
    h("button.wish-main", { type: "button", onclick: () => openWishSheet({ wish: w, onSaved }) },
      h("span.wish-title", w.description),
      h("span.gift-meta",
        wishPrice(w) && h("span.meta-price", wishPrice(w)),
        w.priority === 1 && h("span.prio-high", icon("flag"), PRIORITY[1]),
        w.priority === 3 && h("span", PRIORITY[3]),
        w.archived && w.occasion && h("span", `from ${w.occasion.name}`)),
      w.notes && h("span.gift-notes", w.notes)),
    w.link && h("div.chips.wish-chips", linkChip(w)));
}

/** Plain-text list for the iOS share sheet (Messages, WhatsApp, Notes…). */
export function shareText(name, title, wishes, notes) {
  const lines = [`${name}'s wish list${title ? `: ${title}` : ""}`, ""];
  for (const w of wishes) {
    const bits = [w.description, wishPrice(w), w.priority === 1 && "(really want)"].filter(Boolean);
    lines.push(`• ${bits.join(" — ")}`);
    if (w.notes) lines.push(`  ${w.notes.replace(/\s*\n\s*/g, "; ")}`);
    if (w.link) lines.push(`  ${w.link}`);
  }
  if (notes) lines.push("", `Sizes & notes: ${notes}`);
  return lines.join("\n");
}

export async function shareWishes(name, title, wishes, notes) {
  if (!wishes.length) return toast("Nothing to share yet", "error");
  const text = shareText(name, title, wishes, notes);
  // Phones and tablets: the system share sheet. Computers: show the text, with Copy and Download.
  const touch = window.matchMedia("(pointer: coarse)").matches;
  if (touch && navigator.share) {
    try {
      await navigator.share({ title: `${name}'s wish list`, text });
      return;
    } catch (err) {
      if (err.name === "AbortError") return;
    }
  }
  showShareText(text, title ? `${name}'s wish list: ${title}` : `${name}'s wish list`);
}

function downloadText(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const a = h("a", { href: url, download: filename, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** A window showing the plain text, always readable and selectable even if copying is blocked. */
async function showShareText(text, title) {
  const area = h("textarea.input.share-text", { readonly: true, "aria-label": "Wish list text", rows: 12 });
  area.value = text;
  const filename = `${title.replace(/[^\w\s-]+/g, "").trim().replace(/\s+/g, "-").toLowerCase() || "wish-list"}.txt`;
  const pending = dialog({
    title: "Share wish list",
    body: h("div.stack", h("p.muted", "Copy this into an email or message, or download it."), area),
    actions: [
      { label: "Close", value: null },
      { label: "Download .txt", value: "download" },
      { label: "Copy", value: "copy", primary: true },
    ],
  });
  document.querySelector("dialog.dialog[open]")?.classList.add("dialog-wide");
  area.focus();
  area.select();
  const choice = await pending;
  if (choice === "copy") copyText(text, "Wish list copied, ready to paste");
  if (choice === "download") downloadText(text, filename);
}

/** An occasion that's just for you: the full wish list, front and centre. */
export function myWishesSection(occasion, summary, { onChanged }) {
  const name = summary.me?.name || "My";
  return h("section.section.my-occasion", { "aria-labelledby": "my-wishes-h" },
    h("div.group-head",
      h("h2.section-title#my-wishes-h", "My wish list"),
      h("span.row.row-tight",
        h("span.group-total", summary.count ? summaryText(summary) : ""),
        summary.count > 0 && h("button.btn.btn-icon.btn-ghost", {
          type: "button", "aria-label": `Share my ${occasion.name} list`,
          onclick: () => shareWishes(name, occasion.name, summary.items, summary.me?.notes),
        }, icon("share")))),
    summary.items.length
      ? h("ul.wish-list", summary.items.map((w) => wishRow(w, onChanged)))
      : h("div.empty",
        h("span.empty-star", { "aria-hidden": "true" }),
        h("h3", "What would you like?"),
        h("p.muted", occasion.is_archived ? "Nothing was listed." : "Add things you'd like, or move them here from your wish list.")));
}

/** Card on an occasion page: your wishes for it. */
export function myWishesCard(occasion, summary, { onChanged }) {
  const card = h("section.wish-card", { "aria-labelledby": "my-wishes-h" },
    h("div.wish-card-head",
      h("div",
        h("h2.wish-card-title#my-wishes-h", icon("gift"), "My wish list"),
        h("p.muted.small", summaryText(summary))),
      h("a.btn.btn-sm", { href: `#/me?o=${occasion.id}` }, "See all")),
    summary.items.length > 0 && h("ul.wish-mini", summary.items.slice(0, 3).map((w) =>
      h("li", h("span", w.description), wishPrice(w) && h("span.muted", wishPrice(w))))),
    !occasion.is_archived && h("button.btn.btn-block", {
      type: "button",
      onclick: () => openWishSheet({ occasionId: occasion.id, onSaved: onChanged }),
    }, icon("plus"), `Add a wish for ${occasion.name}`));
  return card;
}
