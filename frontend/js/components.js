import { api } from "./api.js";
import { h, icon, toast, confirmDialog, segmented, radioValue, copyText } from "./dom.js";
import { openSheet, actionSheet, field, moneyInputEl } from "./sheet.js";
import {
  money, parseMoney, moneyInput, STATUSES, STATUS_LABEL, nextStatus, PRIORITIES, PRIORITY_LABEL,
  budgetPhrase, deliveryDay,
} from "./format.js";

// ------------------------------------------------------------------ status

export function statusBadge(status) {
  return h(`span.pill.status-${status}`, h("span.dot"), h("span", STATUS_LABEL[status]));
}

/**
 * Traffic-light pill. Tap moves to the next stage; press-and-hold (or tap on
 * the last stage) opens a menu to pick any stage.
 */
export function statusPill(gift, { readOnly, onChange }) {
  if (readOnly) return statusBadge(gift.status);
  const next = nextStatus(gift.status);
  const btn = h(`button.pill.pill-btn.status-${gift.status}`, {
    type: "button",
    "aria-label": `Status: ${STATUS_LABEL[gift.status]}. ${next ? `Tap to mark ${STATUS_LABEL[next]}; hold for more.` : "Tap to change."}`,
  }, h("span.dot"), h("span", STATUS_LABEL[gift.status]), next && icon("chevron"));

  let timer = null;
  let held = false;
  const cancel = () => { clearTimeout(timer); timer = null; btn.classList.remove("is-pressing"); };
  btn.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    held = false;
    btn.classList.add("is-pressing");
    timer = setTimeout(() => { held = true; cancel(); pickStatus(gift, onChange); }, 450);
  });
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => btn.addEventListener(ev, cancel));
  btn.addEventListener("contextmenu", (e) => e.preventDefault());
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (held) { held = false; return; }
    if (next) onChange(next, gift.status);
    else pickStatus(gift, onChange);
  });
  return btn;
}

async function pickStatus(gift, onChange) {
  const value = await actionSheet({
    title: gift.description,
    message: "Set status",
    actions: STATUSES.map((s) => ({
      label: s.label, value: s.value, dot: true, className: `status-${s.value}`, current: s.value === gift.status,
    })),
  });
  if (value && value !== gift.status) onChange(value, gift.status);
}

/** PATCH a gift's status with an Undo toast. Calls refresh() after each change. */
export async function changeStatus(gift, status, previous, refresh) {
  try {
    await api(`/api/gifts/${gift.id}`, { method: "PATCH", body: { status } });
    await refresh();
    toast(`${gift.description}: ${STATUS_LABEL[status]}`, "ok", {
      action: {
        label: "Undo",
        run: async () => {
          try {
            await api(`/api/gifts/${gift.id}`, { method: "PATCH", body: { status: previous } });
            await refresh();
          } catch (err) {
            toast(err.message, "error");
          }
        },
      },
    });
  } catch (err) {
    toast(err.message, "error");
  }
}

// ------------------------------------------------------------------ budget

export function meter(t, { large = false } = {}) {
  if (t.budget_pence == null || t.budget_pence === 0) {
    return h(`div.meter.meter-none${large ? ".meter-lg" : ""}`, { "aria-hidden": "true" });
  }
  const pct = (v) => `${Math.min(100, (v / t.budget_pence) * 100).toFixed(1)}%`;
  return h(`div.meter.state-${t.state}${large ? ".meter-lg" : ""}`, {
    role: "img",
    "aria-label": `${money(t.spent_pence)} spent of ${money(t.budget_pence)} budget; ${money(t.planned_pence)} including ideas.`,
  },
  h("span.meter-planned", { style: { width: pct(t.planned_pence) } }),
  h("span.meter-spent", { style: { width: pct(t.spent_pence) } }));
}

export function budgetLine(t) {
  return h(`span.budget-phrase.state-${t.state || "none"}`, budgetPhrase(t));
}

/** Small row of coloured dots summarising status counts. */
export function statusDots(counts) {
  const parts = STATUSES.filter((s) => counts[s.value]).map((s) =>
    h(`span.count.status-${s.value}`, { title: s.label }, h("span.dot"), String(counts[s.value])));
  return parts.length ? h("span.counts", { "aria-label": STATUSES.filter((s) => counts[s.value]).map((s) => `${counts[s.value]} ${s.label}`).join(", ") }, parts) : null;
}

// ------------------------------------------------------------------ gift rows

export function giftMeta(g, { showRecipient = false } = {}) {
  const bits = [];
  if (showRecipient) bits.push(h("span.meta-strong", g.recipient_name));
  if (g.price_pence != null) {
    let price = g.quantity > 1 ? `${g.quantity} × ${money(g.price_pence)}` : money(g.price_pence);
    if (g.my_share_pence != null) price += ` · your share ${money(g.my_share_pence)}`;
    bits.push(h("span.meta-price", price));
  } else if (g.my_share_pence != null) {
    bits.push(h("span.meta-price", `Your share ${money(g.my_share_pence)}`));
  }
  if (g.retailer) bits.push(h("span", g.retailer));
  if (g.priority === 1) bits.push(h("span.prio-high", icon("flag"), "High"));
  if (g.priority === 3) bits.push(h("span.prio-low", "Low priority"));
  return bits.length ? h("span.gift-meta", bits) : null;
}

export function trackingChip(g) {
  if (!g.tracking_number) return null;
  return h("button.chip.chip-copy", {
    type: "button",
    "aria-label": `Copy tracking number ${g.tracking_number}`,
    onclick: (e) => { e.stopPropagation(); copyText(g.tracking_number, "Tracking number copied"); },
  }, icon("copy"), h("span.mono", g.tracking_number));
}

export function deliveryChip(g) {
  const d = deliveryDay(g.delivery_date);
  if (!d) return null;
  const late = d.overdue && g.status === "ordered";
  return h(`span.chip${late ? ".chip-late" : ""}`, icon("calendar"), late ? `Due ${d.text}` : d.text);
}

export function linkChip(g) {
  if (!g.link) return null;
  let host = g.link;
  try { host = new URL(g.link).hostname.replace(/^www\./, ""); } catch { /* keep raw */ }
  return h("a.chip.chip-link", {
    href: g.link, target: "_blank", rel: "noopener noreferrer", onclick: (e) => e.stopPropagation(),
  }, icon("link"), h("span", host));
}

export function hidingChip(g) {
  return g.hiding_place ? h("span.chip", icon("pin"), g.hiding_place) : null;
}

// ------------------------------------------------------------------ gift sheet

function textInput(name, value, attrs = {}) {
  return h("input.input", { name, value: value ?? "", autocomplete: "off", enterkeyhint: "next", ...attrs });
}

/**
 * Add/edit a gift. `recipient` supplies the buyer choices (owner + shared users).
 */
export function openGiftSheet({ recipient, gift, readOnly = false, onSaved }) {
  const g = gift || { status: "idea", priority: 2, quantity: 1, buyer: null };
  const members = [recipient.owner, ...recipient.shared_with];
  return openSheet({
    title: gift ? (readOnly ? gift.description : "Edit gift") : `Gift for ${recipient.name}`,
    saveLabel: gift ? "Save" : "Add",
    readOnly,
    build(form, { close }) {
      const fs = h("fieldset.fieldset", { disabled: readOnly });
      fs.append(
        field("What is it?", h("textarea.input.input-title", {
          name: "description", rows: 2, required: true, maxlength: 200, enterkeyhint: "next",
          placeholder: "e.g. Lego Botanicals orchid", value: g.description ?? "",
        })),
        h("div.field", h("span.label", "Status"),
          segmented("status", STATUSES.map((s) => ({ ...s, dot: true, className: `status-${s.value}` })), g.status, { label: "Status" })),
        h("div.field-row",
          field("Price", moneyInputEl("price", moneyInput(g.price_pence)), { optional: true }),
          field("Qty", textInput("quantity", g.quantity ?? 1, { inputmode: "numeric", pattern: "[0-9]*", maxlength: 2 }), { className: "field-qty" })),
        field("Link", textInput("link", g.link, { type: "url", inputmode: "url", autocapitalize: "none", autocorrect: "off", spellcheck: "false", placeholder: "https://" }), { optional: true }),
        h("div.field", h("span.label", "Priority"),
          segmented("priority", PRIORITIES, g.priority, { label: "Priority" })),
        h("h3.form-section", "Order & delivery"),
        field("Retailer", textInput("retailer", g.retailer, { placeholder: "e.g. John Lewis", autocapitalize: "words" }), { optional: true }),
        field("Tracking number", textInput("tracking_number", g.tracking_number, { autocapitalize: "characters", autocorrect: "off", spellcheck: "false" }), { optional: true }),
        field("Expected delivery", h("input.input.input-date", { type: "date", name: "delivery_date", value: g.delivery_date ?? "" }), { optional: true }),
        field("Where it's hidden", textInput("hiding_place", g.hiding_place, { placeholder: "e.g. Top of the wardrobe", autocapitalize: "sentences" }), { optional: true }),
        h("h3.form-section", "Splitting it?"),
        field("Your share", moneyInputEl("my_share", moneyInput(g.my_share_pence)), {
          optional: true, hint: "For a joint gift: what you're paying. This counts towards the budget instead of the full price.",
        }),
        members.length > 1 && field("Who's buying it", h("select.input", { name: "buyer_id" },
          h("option", { value: "" }, "Not decided"),
          members.map((m) => h("option", { value: String(m.id), selected: g.buyer ? g.buyer.id === m.id : false }, m.name)))),
        field("Notes", h("textarea.input", { name: "notes", rows: 3, maxlength: 4000, value: g.notes ?? "", placeholder: "Size, colour, gift receipt…" }), { optional: true }),
      );
      form.append(fs);
      if (gift && !readOnly) {
        form.append(h("button.btn.btn-danger-ghost.btn-block", {
          type: "button",
          onclick: async () => {
            if (!(await confirmDialog("Delete this gift?", `"${gift.description}" will be removed.`))) return;
            try {
              const res = await api(`/api/gifts/${gift.id}`, { method: "DELETE" });
              toast("Gift deleted");
              close();
              onSaved?.(null, res.recipient);
            } catch (err) {
              toast(err.message, "error");
            }
          },
        }, icon("trash"), "Delete gift"));
      }
    },
    async onSave(form) {
      const description = form.description.value.trim();
      if (!description) {
        form.description.focus();
        throw new Error("Describe the gift.");
      }
      const price = parseMoney(form.price.value);
      const share = parseMoney(form.my_share.value);
      if (Number.isNaN(price)) throw new Error("Price should be an amount like 24.99.");
      if (Number.isNaN(share)) throw new Error("Your share should be an amount like 12.50.");
      const qty = Number(form.quantity.value || 1);
      if (!Number.isInteger(qty) || qty < 1 || qty > 99) throw new Error("Quantity should be between 1 and 99.");
      const body = {
        description,
        status: radioValue(form, "status"),
        priority: Number(radioValue(form, "priority")),
        price_pence: price,
        quantity: qty,
        my_share_pence: share,
        link: form.link.value.trim() || null,
        retailer: form.retailer.value,
        tracking_number: form.tracking_number.value,
        delivery_date: form.delivery_date.value || null,
        hiding_place: form.hiding_place.value,
        notes: form.notes.value,
      };
      if (form.buyer_id) body.buyer_id = form.buyer_id.value ? Number(form.buyer_id.value) : null;
      const res = gift
        ? await api(`/api/gifts/${gift.id}`, { method: "PATCH", body })
        : await api(`/api/recipients/${recipient.id}/gifts`, { method: "POST", body });
      toast(gift ? "Gift saved" : "Gift added");
      onSaved?.(res.gift, res.recipient);
    },
  });
}

// ------------------------------------------------------------------ recipient sheet

let directoryCache = null;
export async function directory() {
  if (!directoryCache) directoryCache = (await api("/api/users/directory")).users;
  return directoryCache;
}

let categoriesCache = null;
export async function categories({ fresh = false } = {}) {
  if (!categoriesCache || fresh) categoriesCache = (await api("/api/categories")).categories;
  return categoriesCache;
}
export function invalidateCategories() { categoriesCache = null; }

export async function openRecipientSheet({ recipient, me, onSaved, onDeleted }) {
  const [cats, people] = await Promise.all([categories({ fresh: true }), directory()]);
  const r = recipient || { name: "", budget_pence: null, notes: "", category: null, shared_with: [] };
  const isOwner = !recipient || recipient.is_owner;
  const others = people.filter((p) => p.id !== (recipient?.owner.id ?? me.id));
  const sharedIds = new Set(r.shared_with.map((p) => p.id));

  return openSheet({
    title: recipient ? "Edit person" : "Add person",
    saveLabel: recipient ? "Save" : "Add",
    build(form, { close }) {
      form.append(
        field("Name", textInput("name", r.name, { required: true, maxlength: 80, autocapitalize: "words", placeholder: "e.g. Molly" })),
        field("Budget", moneyInputEl("budget", moneyInput(r.budget_pence)), {
          optional: true, hint: "What you plan to spend. The tally shows under, on or over.",
        }),
        cats.length > 0 && field("Category", h("select.input", { name: "category_id" },
          h("option", { value: "" }, "No category"),
          cats.map((c) => h("option", { value: String(c.id), selected: r.category?.id === c.id }, c.name)))),
        field("Notes", h("textarea.input", { name: "notes", rows: 3, maxlength: 4000, value: r.notes ?? "", placeholder: "Sizes, likes, things to avoid…" }), { optional: true }),
      );
      if (isOwner && others.length) {
        form.append(h("fieldset.fieldset.share-list",
          h("legend.label", "Share with"),
          h("p.hint", "People you share with can see and edit this person's gifts. Everyone else can't see them at all."),
          others.map((p) => h("label.check-row",
            h("input", { type: "checkbox", name: "share", value: String(p.id), checked: sharedIds.has(p.id) }),
            h("span.check-box", { "aria-hidden": "true" }, icon("check")),
            h("span", p.name)))));
      }
      if (recipient && isOwner) {
        form.append(h("button.btn.btn-danger-ghost.btn-block", {
          type: "button",
          onclick: async () => {
            const n = recipient.totals.gift_count;
            if (!(await confirmDialog(`Delete ${recipient.name}?`, n ? `Their ${n} gift${n === 1 ? "" : "s"} will be deleted too.` : "They'll be removed from this season."))) return;
            try {
              await api(`/api/recipients/${recipient.id}`, { method: "DELETE" });
              toast(`${recipient.name} deleted`);
              close();
              onDeleted?.();
            } catch (err) {
              toast(err.message, "error");
            }
          },
        }, icon("trash"), "Delete person"));
      }
    },
    async onSave(form) {
      const name = form.name.value.trim();
      if (!name) throw new Error("Give them a name.");
      const budget = parseMoney(form.budget.value);
      if (Number.isNaN(budget)) throw new Error("Budget should be an amount like 300.");
      const body = {
        name,
        budget_pence: budget,
        notes: form.notes.value,
        category_id: form.category_id?.value ? Number(form.category_id.value) : null,
      };
      let res = recipient
        ? await api(`/api/recipients/${recipient.id}`, { method: "PATCH", body })
        : await api("/api/recipients", { method: "POST", body });
      if (isOwner && others.length) {
        const ids = Array.from(form.querySelectorAll('input[name="share"]:checked')).map((i) => Number(i.value));
        const before = [...sharedIds].sort().join();
        if (ids.sort().join() !== before) {
          res = await api(`/api/recipients/${res.recipient.id}/shares`, { method: "PUT", body: { user_ids: ids } });
        }
      }
      toast(recipient ? "Saved" : `${name} added`);
      onSaved?.(res.recipient);
    },
  });
}

// ------------------------------------------------------------------ seasons

export async function pickSeason(current, navigate, base = "/") {
  const { seasons } = await api("/api/seasons");
  const value = await actionSheet({
    title: "Season",
    message: "Archived seasons are read-only.",
    actions: seasons.map((s) => ({
      label: s.is_archived ? `${s.name} (archived)` : s.name, value: s, current: s.id === current.id,
    })),
  });
  if (!value || value.id === current.id) return;
  navigate(value.is_archived ? `${base}?season=${value.id}` : base);
}

export function archivedBanner(season, navigate, base = "/") {
  return h("div.banner", { role: "note" }, icon("archive"),
    h("p", h("strong", season.name), " is archived and read-only."),
    h("button.btn.btn-sm", { type: "button", onclick: () => navigate(base) }, "Current season"));
}

export { PRIORITY_LABEL };
