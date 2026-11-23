import { api } from "./api.js";
import { h, icon, toast, confirmDialog, segmented, radioValue, copyText } from "./dom.js";
import { openSheet, actionSheet, field, moneyInputEl } from "./sheet.js";
import {
  money, parseMoney, moneyInput, STATUSES, STATUS_LABEL, nextStatus, PRIORITIES, PRIORITY_LABEL,
  budgetPhrase, deliveryDay, KINDS,
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

function personFields(p, cats, { hint } = {}) {
  return [
    field("Name", textInput("name", p.name, { required: true, maxlength: 80, autocapitalize: "words", placeholder: "e.g. Molly" })),
    cats.length > 0 && field("Category", h("select.input", { name: "category_id" },
      h("option", { value: "" }, "No category"),
      cats.map((c) => h("option", { value: String(c.id), selected: p.category?.id === c.id }, c.name)))),
    field("Notes", h("textarea.input", { name: "notes", rows: 3, maxlength: 4000, value: p.notes ?? "", placeholder: "Sizes, likes, things to avoid…" }), {
      optional: true, hint,
    }),
  ];
}

function readPersonFields(form) {
  const name = form.name.value.trim();
  if (!name) throw new Error("Give them a name.");
  return {
    name,
    notes: form.notes.value,
    category_id: form.category_id?.value ? Number(form.category_id.value) : null,
  };
}

function shareFieldset(others, sharedIds) {
  if (!others.length) return null;
  return h("fieldset.fieldset.share-list",
    h("legend.label", "Share with"),
    h("p.hint", "People you share with can see and edit their gifts in this occasion. Everyone else can't see them at all."),
    others.map((p) => h("label.check-row",
      h("input", { type: "checkbox", name: "share", value: String(p.id), checked: sharedIds.has(p.id) }),
      h("span.check-box", { "aria-hidden": "true" }, icon("check")),
      h("span", p.name))));
}

function checkedShares(form) {
  return Array.from(form.querySelectorAll('input[name="share"]:checked')).map((i) => Number(i.value));
}

function budgetField(value) {
  return field("Budget", moneyInputEl("budget", moneyInput(value)), {
    optional: true, hint: "For this occasion. The tally shows under, on or over.",
  });
}

function readBudget(form) {
  const budget = parseMoney(form.budget.value);
  if (Number.isNaN(budget)) throw new Error("Budget should be an amount like 300.");
  return budget;
}

/** Edit someone's entry in an occasion: their details (shared everywhere) plus budget and sharing here. */
export async function openRecipientSheet({ recipient, me, onSaved, onRemoved }) {
  const [cats, users] = await Promise.all([categories({ fresh: true }), directory()]);
  const r = recipient;
  const isOwner = r.is_owner;
  const others = users.filter((p) => p.id !== r.owner.id);
  const sharedIds = new Set(r.shared_with.map((p) => p.id));
  const linked = isOwner ? (await api("/api/people")).people.find((p) => p.id === r.person_id) : null;
  const elsewhere = (linked?.entries || []).filter((e) => e.recipient_id !== r.id).map((e) => e.occasion.name);

  return openSheet({
    title: `Edit ${r.name}`,
    build(form, { close }) {
      if (isOwner) {
        form.append(...personFields(r, cats, {
          hint: elsewhere.length ? `Name, category and notes are shared with ${elsewhere.join(", ")}.` : null,
        }).filter(Boolean));
      } else {
        form.append(h("p.muted", `${r.owner.name} added ${r.name}. They can change their name and notes.`));
      }
      form.append(budgetField(r.budget_pence));
      if (isOwner) form.append(shareFieldset(others, sharedIds) || "");
      if (isOwner) {
        form.append(h("button.btn.btn-danger-ghost.btn-block", {
          type: "button",
          onclick: async () => {
            const n = r.totals.gift_count;
            const ok = await confirmDialog(`Remove ${r.name} from ${r.occasion.name}?`,
              `${n ? `Their ${n} gift${n === 1 ? "" : "s"} here will be deleted. ` : ""}${r.name} stays in your People${elsewhere.length ? ` and in ${elsewhere.join(", ")}` : ""}.`, "Remove");
            if (!ok) return;
            try {
              await api(`/api/recipients/${r.id}`, { method: "DELETE" });
              toast(`${r.name} removed from ${r.occasion.name}`);
              close();
              onRemoved?.();
            } catch (err) {
              toast(err.message, "error");
            }
          },
        }, icon("trash"), `Remove from ${r.occasion.name}`));
      }
    },
    async onSave(form) {
      const body = { budget_pence: readBudget(form) };
      if (isOwner) Object.assign(body, readPersonFields(form));
      let res = await api(`/api/recipients/${r.id}`, { method: "PATCH", body });
      if (isOwner && others.length) {
        const ids = checkedShares(form);
        if (ids.slice().sort().join() !== [...sharedIds].sort().join()) {
          res = await api(`/api/recipients/${r.id}/shares`, { method: "PUT", body: { user_ids: ids } });
        }
      }
      toast("Saved");
      onSaved?.(res.recipient);
    },
  });
}

/** Add someone to an occasion: one of your people, or someone new. */
export async function openAddPersonSheet({ occasion, me, onSaved }) {
  const [cats, users, { people }] = await Promise.all([categories({ fresh: true }), directory(), api("/api/people")]);
  const available = people.filter((p) => !p.entries.some((e) => e.occasion.id === occasion.id));
  const others = users.filter((p) => p.id !== me.id);
  let mode = available.length ? "existing" : "new";

  return openSheet({
    title: `Add to ${occasion.name}`,
    saveLabel: "Add",
    build(form) {
      const existing = h("div.stack",
        h("fieldset.fieldset.pick-list",
          h("legend.label", "Your people"),
          available.map((p, i) => h("label.radio-row",
            h("input", { type: "radio", name: "person_id", value: String(p.id), checked: i === 0 }),
            h("span.radio-dot", { "aria-hidden": "true" }),
            h("span.radio-text", h("span.radio-title", p.name),
              (p.category || p.entries.length > 0) && h("span.radio-sub",
                [p.category?.name, p.entries[0] && `last in ${p.entries[0].occasion.name}`].filter(Boolean).join(" · ")))))));
      const fresh = h("div.stack", ...personFields({ name: "", notes: "", category: null }, cats).filter(Boolean));
      const show = () => {
        existing.hidden = mode !== "existing";
        fresh.hidden = mode !== "new";
        // Hidden inputs must not block submission or be read.
        fresh.querySelectorAll("input, select, textarea").forEach((el) => { el.disabled = mode !== "new"; });
        existing.querySelectorAll("input").forEach((el) => { el.disabled = mode !== "existing"; });
      };
      if (available.length) {
        form.append(segmented("mode", [{ value: "existing", label: "Existing person" }, { value: "new", label: "Someone new" }], mode, {
          label: "Who", onchange: (v) => { mode = v; show(); },
        }));
      }
      form.append(existing, fresh, budgetField(null), shareFieldset(others, new Set()) || "");
      show();
    },
    async onSave(form) {
      const body = { budget_pence: readBudget(form), share_user_ids: checkedShares(form) };
      if (mode === "existing") {
        const picked = form.querySelector('input[name="person_id"]:checked');
        if (!picked) throw new Error("Pick someone.");
        body.person_id = Number(picked.value);
      } else {
        Object.assign(body, readPersonFields(form));
      }
      const res = await api(`/api/occasions/${occasion.id}/recipients`, { method: "POST", body });
      toast(`${res.recipient.name} added`);
      onSaved?.(res.recipient);
    },
  });
}

/** Create or edit a person on the People page. */
export async function openPersonSheet({ person, onSaved }) {
  const cats = await categories({ fresh: true });
  const p = person || { name: "", notes: "", category: null, entries: [] };
  return openSheet({
    title: person ? person.name : "New person",
    saveLabel: person ? "Save" : "Add",
    build(form, { close }) {
      form.append(...personFields(p, cats, { hint: person && p.entries.length > 1 ? "Shown in every occasion they're in." : null }).filter(Boolean));
      if (person) {
        form.append(h("div.field", h("span.label", "Occasions"),
          p.entries.length
            ? h("ul.entry-list", p.entries.map((e) => h("li", h("a.entry-link", { href: `#/r/${e.recipient_id}`, onclick: () => close() },
              h("span", e.occasion.name),
              h("span.muted", [e.occasion.is_archived && "Archived", e.budget_pence != null && `Budget ${money(e.budget_pence)}`].filter(Boolean).join(" · ")),
              icon("chevron")))))
            : h("p.muted", "Not in any occasion yet. Add them from an occasion's page.")));
        form.append(h("button.btn.btn-danger-ghost.btn-block", {
          type: "button",
          disabled: p.entries.length > 0,
          onclick: async () => {
            if (!(await confirmDialog(`Delete ${p.name}?`, "They'll be removed from your People."))) return;
            try {
              await api(`/api/people/${p.id}`, { method: "DELETE" });
              toast(`${p.name} deleted`);
              close();
              onSaved?.();
            } catch (err) {
              toast(err.message, "error");
            }
          },
        }, icon("trash"), "Delete person"),
        p.entries.length > 0 && h("p.hint.center", "Remove them from every occasion before deleting."));
      }
    },
    async onSave(form) {
      const body = readPersonFields(form);
      const res = person
        ? await api(`/api/people/${person.id}`, { method: "PATCH", body })
        : await api("/api/people", { method: "POST", body });
      toast(person ? "Saved" : `${res.person.name} added`);
      onSaved?.(res.person);
    },
  });
}

// ------------------------------------------------------------------ occasions

function suggestName(kind, personNames, existing = [], dateValue = "") {
  const now = new Date();
  const year = dateValue ? Number(dateValue.slice(0, 4)) : now.getFullYear();
  if (kind === "christmas") {
    // After Boxing Day, or if this year's exists already, suggest next year's.
    const past = !dateValue && now.getMonth() === 11 && now.getDate() > 26;
    const taken = !dateValue && existing.some((n) => n.toLowerCase() === `christmas ${year}`);
    return `Christmas ${past || taken ? year + 1 : year}`;
  }
  if (kind === "birthday") return personNames.length === 1 ? `${personNames[0]}'s birthday ${year}` : `Birthday ${year}`;
  return "";
}

/** New occasion: type, name, date, and who to bring in (optionally copying from another occasion). */
export async function openNewOccasionSheet({ onSaved }) {
  const [{ people }, { occasions }] = await Promise.all([api("/api/people"), api("/api/occasions")]);
  let kind = "christmas";
  let nameTouched = false;

  return openSheet({
    title: "New occasion",
    saveLabel: "Create",
    build(form) {
      const nameInput = textInput("name", suggestName(kind, [], occasions.map((o) => o.name)), { required: true, maxlength: 80, autocapitalize: "words" });
      nameInput.addEventListener("input", () => { nameTouched = true; });
      const picked = () => people.filter((p) => form.querySelector(`input[name="person"][value="${p.id}"]`)?.checked);
      const dateInput = h("input.input.input-date", { type: "date", name: "date" });
      let dateTouched = false;
      dateInput.addEventListener("input", () => { dateTouched = true; refreshName(); });
      const refreshName = () => {
        if (!nameTouched) nameInput.value = suggestName(kind, picked().map((p) => p.name), occasions.map((o) => o.name), dateInput.value);
        // Christmas has a known date: fill it in until the user picks one.
        if (!dateTouched) {
          const y = nameInput.value.match(/\b(20\d\d)\b/)?.[1];
          dateInput.value = kind === "christmas" && y ? `${y}-12-25` : "";
        }
      };

      const copyFrom = h("select.input", { name: "copy_from" },
        h("option", { value: "" }, "Nobody (start empty)"),
        occasions.map((o) => h("option", { value: String(o.id) }, o.is_archived ? `${o.name} (archived)` : o.name)));
      const copyOpts = h("fieldset.fieldset.copy-opts", { hidden: true },
        h("legend.label", "Copy from there"),
        ...[["copy_budgets", "Budgets", true], ["copy_sharing", "Sharing", true], ["copy_gifts", "Gifts (reset to Idea, order details cleared)", false]]
          .map(([name, label, on]) => h("label.check-row",
            h("input", { type: "checkbox", name, checked: on }),
            h("span.check-box", { "aria-hidden": "true" }, icon("check")), h("span", label))),
        h("p.hint", "Names, notes and categories are linked, so they always come along."));
      const list = h("div.people-picks",
        people.length
          ? people.map((p) => h("label.check-row",
            h("input", { type: "checkbox", name: "person", value: String(p.id), onchange: refreshName }),
            h("span.check-box", { "aria-hidden": "true" }, icon("check")),
            h("span.radio-text", h("span.radio-title", p.name), p.category && h("span.radio-sub", p.category.name))))
          : h("p.muted", "You haven't added anyone yet. You can add people after creating it."));
      copyFrom.addEventListener("change", () => {
        const id = Number(copyFrom.value);
        copyOpts.hidden = !id;
        // Pre-tick everyone of yours who's in the chosen occasion.
        for (const p of people) {
          const box = form.querySelector(`input[name="person"][value="${p.id}"]`);
          if (box) box.checked = id ? p.entries.some((e) => e.occasion.id === id) : false;
        }
        refreshName();
      });

      form.append(
        h("div.field", h("span.label", "Type"), segmented("kind", KINDS, kind, {
          label: "Type", onchange: (v) => { kind = v; refreshName(); },
        })),
        field("Name", nameInput),
        field("Date", dateInput, { optional: true, hint: "Used to sort occasions and count down." }),
        h("h3.form-section", "Who's it for?"),
        people.length > 0 && occasions.length > 0 && field("Bring people in from", copyFrom),
        copyOpts,
        list,
      );
      refreshName();
    },
    async onSave(form) {
      const name = form.name.value.trim();
      if (!name) throw new Error("Give the occasion a name.");
      const copyFromId = form.copy_from?.value ? Number(form.copy_from.value) : null;
      const body = {
        kind,
        name,
        date: form.date.value || null,
        person_ids: Array.from(form.querySelectorAll('input[name="person"]:checked')).map((i) => Number(i.value)),
        copy_from_id: copyFromId,
        copy_budgets: form.copy_budgets.checked,
        copy_sharing: form.copy_sharing.checked,
        copy_gifts: form.copy_gifts.checked,
      };
      const res = await api("/api/occasions", { method: "POST", body });
      toast(`${res.occasion.name} created`);
      onSaved?.(res.occasion);
    },
  });
}

export function openEditOccasionSheet({ occasion, onSaved }) {
  let kind = occasion.kind;
  return openSheet({
    title: "Edit occasion",
    build(form) {
      form.append(
        h("div.field", h("span.label", "Type"), segmented("kind", KINDS, kind, { label: "Type", onchange: (v) => { kind = v; } })),
        field("Name", textInput("name", occasion.name, { required: true, maxlength: 80, autocapitalize: "words" })),
        field("Date", h("input.input.input-date", { type: "date", name: "date", value: occasion.date ?? "" }), { optional: true }),
      );
    },
    async onSave(form) {
      const name = form.name.value.trim();
      if (!name) throw new Error("Give the occasion a name.");
      const res = await api(`/api/occasions/${occasion.id}`, { method: "PATCH", body: { name, kind, date: form.date.value || null } });
      toast("Saved");
      onSaved?.(res.occasion);
    },
  });
}

export async function setArchived(occasion, archived) {
  const res = await api(`/api/occasions/${occasion.id}/${archived ? "archive" : "unarchive"}`, { method: "POST" });
  toast(archived ? `${occasion.name} archived` : `${occasion.name} is active again`);
  return res.occasion;
}

/** Occasion actions: edit, archive/unarchive, delete. */
export async function occasionMenu(data, { onChanged, onDeleted }) {
  const o = data.occasion;
  const value = await actionSheet({
    title: o.name,
    actions: [
      !o.is_archived && { label: "Edit details", value: "edit" },
      { label: o.is_archived ? "Unarchive" : "Archive", value: "archive" },
      { label: "Delete occasion", value: "delete", className: "is-danger" },
    ].filter(Boolean),
  });
  try {
    if (value === "edit") openEditOccasionSheet({ occasion: o, onSaved: onChanged });
    if (value === "archive") onChanged(await setArchived(o, !o.is_archived));
    if (value === "delete") {
      const d = data.delete_impact || { recipients: 0, gifts: 0 };
      const parts = [d.recipients && `${d.recipients} ${d.recipients === 1 ? "entry" : "entries"}`, d.gifts && `${d.gifts} gift${d.gifts === 1 ? "" : "s"}`].filter(Boolean);
      const ok = await confirmDialog(`Delete ${o.name}?`,
        `${parts.length ? `This permanently deletes ${parts.join(" and ")} in it. ` : ""}Your People are kept. ${o.is_archived ? "" : "Archiving keeps everything instead."}`, "Delete");
      if (!ok) return;
      await api(`/api/occasions/${o.id}`, { method: "DELETE" });
      toast(`${o.name} deleted`);
      onDeleted();
    }
  } catch (err) {
    toast(err.message, "error");
  }
}

export function archivedBanner(occasion, onUnarchive) {
  return h("div.banner", { role: "note" }, icon("archive"),
    h("p", h("strong", occasion.name), " is archived and read-only."),
    occasion.can_manage && onUnarchive && h("button.btn.btn-sm", { type: "button", onclick: onUnarchive }, "Unarchive"));
}

export { PRIORITY_LABEL };
