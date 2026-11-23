import { api } from "../api.js";
import { h, icon, reveal, clear, toast, dialog, confirmDialog, copyText, busy, formError, skeletonLines } from "../dom.js";
import { money, parseMoney, moneyInput } from "../format.js";
import { openSheet, field, moneyInputEl } from "../sheet.js";
import { invalidateCategories } from "../components.js";

const TABS = [
  { id: "people", label: "People" },
  { id: "categories", label: "Categories" },
  { id: "seasons", label: "Seasons" },
  { id: "settings", label: "Settings" },
];

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const when = (iso) => (iso ? dateFmt.format(new Date(iso)) : "");

export async function render(main, ctx) {
  const tab = TABS.some((t) => t.id === ctx.query.get("tab")) ? ctx.query.get("tab") : "people";
  const body = h("div.admin-body");
  const head = h("header.page-head",
    h("p.eyebrow", "Admin"),
    h("h1.page-title", "Settings & people"),
    h("nav.tabs", { "aria-label": "Admin sections" },
      TABS.map((t) => h("a.tab-link", { href: `#/admin?tab=${t.id}`, "aria-current": t.id === tab ? "page" : null }, t.label))));
  reveal(head, body);
  main.append(h("div.page.admin", head, body));
  body.append(...skeletonLines());
  ctx.setSeasonTag(null);
  const views = { people, categories, seasons, settings };
  await views[tab](body, ctx);
}

function section(title, ...children) {
  return h("section.section", h("h2.section-title", title), ...children);
}

async function showSecret(title, text, message, { shareTitle } = {}) {
  const canShare = shareTitle && navigator.share;
  const value = await dialog({
    title,
    body: h("div.stack", h("p.muted", message), h("p.secret.mono", text)),
    actions: [
      canShare && { label: "Share…", value: "share" },
      { label: "Copy", value: "copy", primary: !canShare },
      { label: "Done", value: null, primary: Boolean(canShare) },
    ].filter(Boolean),
  });
  if (value === "copy") await copyText(text);
  if (value === "share") {
    try { await navigator.share({ title: shareTitle, url: text }); } catch { /* cancelled */ }
  }
}

// ------------------------------------------------------------------ people & invites

async function people(host, ctx) {
  const [{ users }, { invites }] = await Promise.all([api("/api/users"), api("/api/invites")]);
  clear(host);
  const me = ctx.session.user;
  const reload = () => people(host, ctx);

  const userList = h("ul.admin-list", users.map((u) => h("li.admin-row",
    h("div.admin-main",
      h("p.admin-title", u.name, u.id === me.id && h("span.muted", " (you)")),
      h("p.admin-sub", `@${u.username}`,
        u.role === "admin" && h("span.tag", "Admin"),
        !u.is_active && h("span.tag.tag-off", "Deactivated"),
        u.must_change_password && h("span.tag", "Temp password"))),
    u.id !== me.id && h("button.btn.btn-icon", { type: "button", "aria-label": `Manage ${u.name}`, onclick: () => manageUser(u, reload) }, icon("pencil")))));

  const openInvites = invites.filter((i) => i.state === "open");
  const pastInvites = invites.filter((i) => i.state !== "open").slice(0, 10);

  host.append(
    section("People", userList,
      h("div.row",
        h("button.btn", { type: "button", onclick: () => createUser(reload) }, icon("plus"), "Add account"),
        h("button.btn.btn-primary", { type: "button", onclick: () => createInvite(reload) }, icon("share"), "Invite link"))),
    section("Invite links",
      h("p.muted.small", "Each link works once and expires after 7 days. Only a hash is stored, so a link can't be shown again: make a new one if it's lost."),
      openInvites.length || pastInvites.length
        ? h("ul.admin-list",
          [...openInvites, ...pastInvites].map((i) => h("li.admin-row",
            h("div.admin-main",
              h("p.admin-title", i.note || "Invite"),
              h("p.admin-sub",
                h(`span.tag.tag-${i.state}`, i.state === "open" ? "Open" : i.state === "used" ? "Used" : "Expired"),
                i.state === "used" ? `by ${i.used_by || "deleted user"}` : i.state === "open" ? `until ${when(i.expires_at)}` : when(i.expires_at),
                i.make_admin && h("span.tag", "Admin"))),
            i.state === "open" && h("button.btn.btn-sm.btn-danger-ghost", {
              type: "button",
              onclick: async () => {
                if (!(await confirmDialog("Revoke invite?", "The link will stop working."))) return;
                await api(`/api/invites/${i.id}`, { method: "DELETE" });
                toast("Invite revoked");
                reload();
              },
            }, "Revoke"))))
        : h("p.muted", "No invites yet.")),
  );
}

function createUser(reload) {
  openSheet({
    title: "Add account",
    saveLabel: "Create",
    build(form) {
      form.append(
        h("p.muted", "They'll get a temporary password and choose their own on first sign-in."),
        field("Username", { name: "username", required: true, autocapitalize: "none", autocorrect: "off", spellcheck: "false", autocomplete: "off" }),
        field("Display name", { name: "display_name", autocapitalize: "words", autocomplete: "off" }, { optional: true }),
        h("label.check-row", h("input", { type: "checkbox", name: "admin" }), h("span.check-box", { "aria-hidden": "true" }, icon("check")), h("span", "Administrator")));
    },
    async onSave(form) {
      const res = await api("/api/users", {
        method: "POST",
        body: { username: form.username.value.trim(), display_name: form.display_name.value.trim() || null, role: form.admin.checked ? "admin" : "user" },
      });
      reload();
      setTimeout(() => showSecret("Temporary password", res.temporary_password, `Give this to ${res.user.name}. It's shown only once.`), 250);
    },
  });
}

function createInvite(reload) {
  openSheet({
    title: "New invite link",
    saveLabel: "Create",
    build(form) {
      form.append(
        field("Who's it for?", { name: "note", autocapitalize: "words", placeholder: "e.g. Sam", autocomplete: "off" }, { optional: true, hint: "Just a label so you know which link is which." }),
        h("label.check-row", h("input", { type: "checkbox", name: "admin" }), h("span.check-box", { "aria-hidden": "true" }, icon("check")), h("span", "Make them an administrator")));
    },
    async onSave(form) {
      const res = await api("/api/invites", { method: "POST", body: { note: form.note.value.trim() || null, make_admin: form.admin.checked } });
      const url = `${location.origin}${res.path}`;
      reload();
      setTimeout(() => showSecret("Invite link", url, "Send this link. It works once and is shown only now.", { shareTitle: "Christmas List invite" }), 250);
    },
  });
}

function manageUser(u, reload) {
  openSheet({
    title: u.name,
    readOnly: true,
    build(form, { close }) {
      const act = (label, fn, cls = "btn") => h(`button.${cls.split(" ").join(".")}.btn-block`, {
        type: "button",
        onclick: async (e) => {
          try {
            if ((await busy(e.currentTarget, fn)) === false) return;
            close();
            reload();
          } catch (err) {
            form.prepend(formError(err.message));
          }
        },
      }, label);
      form.append(
        h("p.muted", `@${u.username} · joined ${when(u.created_at)}${u.last_login_at ? ` · last seen ${when(u.last_login_at)}` : ""}`),
        h("div.stack",
          act("Reset password", async () => {
            const res = await api(`/api/users/${u.id}/reset-password`, { method: "POST" });
            setTimeout(() => showSecret("Temporary password", res.temporary_password, `Give this to ${u.name}. They've been signed out everywhere.`), 250);
          }),
          act(u.role === "admin" ? "Remove administrator" : "Make administrator", () =>
            api(`/api/users/${u.id}`, { method: "PATCH", body: { role: u.role === "admin" ? "user" : "admin" } })),
          act(u.is_active ? "Deactivate" : "Reactivate", () =>
            api(`/api/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } })),
          act("Delete account", async () => {
            if (!(await confirmDialog(`Delete ${u.name}?`, "Their account and every person and gift they added will be permanently deleted."))) return false;
            await api(`/api/users/${u.id}`, { method: "DELETE" });
            toast("Account deleted");
          }, "btn btn-danger-ghost")));
    },
  });
}

// ------------------------------------------------------------------ categories

async function categories(host) {
  const { categories: cats } = await api("/api/categories");
  clear(host);
  const reload = () => { invalidateCategories(); return categories(host); };
  const move = async (i, delta) => {
    const ids = cats.map((c) => c.id);
    [ids[i], ids[i + delta]] = [ids[i + delta], ids[i]];
    await api("/api/categories/order", { method: "PUT", body: { ids } });
    reload();
  };
  const err = h("div", { "aria-live": "assertive" });
  const input = h("input.input", { name: "name", placeholder: "e.g. Kids", autocapitalize: "words", autocomplete: "off", enterkeyhint: "done", "aria-label": "New category name" });
  const add = h("form.inline-form", {
    onsubmit: async (e) => {
      e.preventDefault();
      err.replaceChildren();
      if (!input.value.trim()) return;
      try {
        await api("/api/categories", { method: "POST", body: { name: input.value } });
        reload();
      } catch (ex) {
        err.append(formError(ex.message));
      }
    },
  }, input, h("button.btn.btn-primary", { type: "submit" }, icon("plus"), "Add"));

  host.append(section("Categories",
    h("p.muted.small", "Optional groups for the overview, each with its own subtotal. People without one appear under Uncategorised."),
    err, add,
    cats.length ? h("ul.admin-list", cats.map((c, i) => h("li.admin-row",
      h("div.admin-main", h("p.admin-title", c.name)),
      h("div.row.row-tight",
        h("button.btn.btn-icon", { type: "button", "aria-label": `Move ${c.name} up`, disabled: i === 0, onclick: () => move(i, -1) }, icon("up")),
        h("button.btn.btn-icon", { type: "button", "aria-label": `Move ${c.name} down`, disabled: i === cats.length - 1, onclick: () => move(i, 1) }, icon("down")),
        h("button.btn.btn-icon", { type: "button", "aria-label": `Rename ${c.name}`, onclick: () => renameCategory(c, reload) }, icon("pencil")),
        h("button.btn.btn-icon.btn-danger-ghost", {
          type: "button", "aria-label": `Delete ${c.name}`,
          onclick: async () => {
            if (!(await confirmDialog(`Delete "${c.name}"?`, "People in it become uncategorised. Nothing else is deleted."))) return;
            await api(`/api/categories/${c.id}`, { method: "DELETE" });
            reload();
          },
        }, icon("trash")))))) : h("p.muted", "No categories yet.")));
}

function renameCategory(c, reload) {
  openSheet({
    title: "Rename category",
    build(form) { form.append(field("Name", { name: "name", value: c.name, required: true, autocapitalize: "words" })); },
    async onSave(form) {
      await api(`/api/categories/${c.id}`, { method: "PATCH", body: { name: form.name.value } });
      reload();
    },
  });
}

// ------------------------------------------------------------------ seasons

async function seasons(host, ctx) {
  const { seasons: list } = await api("/api/seasons");
  clear(host);
  const reload = () => seasons(host, ctx);
  const active = list.find((s) => !s.is_archived);
  const archived = list.filter((s) => s.is_archived);
  const year = new Date().getFullYear();
  const suggested = active?.name.includes(String(year)) ? `Christmas ${year + 1}` : `Christmas ${year}`;

  host.append(
    section("Current season",
      active ? h("div.admin-row.card-row",
        h("div.admin-main", h("p.admin-title", active.name), h("p.admin-sub", `Started ${when(active.created_at)}`)),
        h("button.btn.btn-icon", { type: "button", "aria-label": "Rename season", onclick: () => renameSeason(active, reload) }, icon("pencil"))) : h("p.muted", "None."),
      h("button.btn.btn-primary.btn-block", { type: "button", onclick: () => startSeason(active, suggested, reload) }, icon("archive"), "Archive & start a new season")),
    section("Archived",
      archived.length ? h("ul.admin-list", archived.map((s) => h("li.admin-row",
        h("div.admin-main", h("p.admin-title", s.name), h("p.admin-sub", `Archived ${when(s.archived_at)}`)),
        h("div.row.row-tight",
          h("a.btn.btn-sm", { href: `#/?season=${s.id}` }, "View"),
          h("button.btn.btn-sm", {
            type: "button",
            onclick: async () => {
              if (!(await confirmDialog(`Make ${s.name} current?`, `${active ? `${active.name} will be archived. ` : ""}You can switch back at any time.`, "Make current", { danger: false }))) return;
              await api(`/api/seasons/${s.id}/activate`, { method: "POST" });
              toast(`${s.name} is now the current season`);
              reload();
            },
          }, "Make current"))))) : h("p.muted", "No archived seasons yet.")),
  );
}

function renameSeason(s, reload) {
  openSheet({
    title: "Rename season",
    build(form) { form.append(field("Name", { name: "name", value: s.name, required: true, autocapitalize: "words" })); },
    async onSave(form) {
      await api(`/api/seasons/${s.id}`, { method: "PATCH", body: { name: form.name.value } });
      reload();
    },
  });
}

function startSeason(active, suggested, reload) {
  openSheet({
    title: "New season",
    saveLabel: "Start",
    build(form) {
      const copyGifts = h("input", { type: "checkbox", name: "copy_gifts" });
      const copyPeople = h("input", { type: "checkbox", name: "copy_recipients", checked: true, onchange: () => {
        copyGifts.disabled = !copyPeople.checked;
        if (!copyPeople.checked) copyGifts.checked = false;
      } });
      form.append(
        field("Name", { name: "name", value: suggested, required: true, autocapitalize: "words" }),
        active && h("p.muted", h("strong", active.name), " will be archived. It stays viewable, read-only."),
        active && h("fieldset.fieldset",
          h("legend.label", `Copy from ${active.name}`),
          h("label.check-row", copyPeople, h("span.check-box", { "aria-hidden": "true" }, icon("check")),
            h("span", "People, with budgets, notes, categories and sharing")),
          h("label.check-row", copyGifts, h("span.check-box", { "aria-hidden": "true" }, icon("check")),
            h("span", "Gifts too, reset to Idea (tracking, delivery and hiding place cleared)"))));
    },
    async onSave(form) {
      const name = form.name.value.trim();
      if (!name) throw new Error("Give the season a name.");
      await api("/api/seasons", {
        method: "POST",
        body: { name, copy_recipients: form.copy_recipients?.checked ?? false, copy_gifts: form.copy_gifts?.checked ?? false },
      });
      toast(`${name} started`);
      reload();
    },
  });
}

// ------------------------------------------------------------------ settings

async function settings(host) {
  const { settings: s } = await api("/api/settings");
  clear(host);
  const err = h("div", { "aria-live": "assertive" });
  const save = h("button.btn.btn-primary", { type: "submit", dataset: { busyLabel: "Saving…" } }, "Save");
  const form = h("form.form.card", { novalidate: true },
    err,
    field("“On budget” margin", moneyInputEl("margin", moneyInput(s.budget_margin_pence)), {
      hint: `Spending within this much either side of a budget counts as on budget. Currently ±${money(s.budget_margin_pence)}.`,
    }),
    save);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.replaceChildren();
    const v = parseMoney(form.margin.value);
    if (v == null || Number.isNaN(v)) { err.append(formError("Enter an amount, e.g. 5.")); return; }
    await busy(save, async () => {
      try {
        await api("/api/settings", { method: "PUT", body: { budget_margin_pence: v } });
        toast("Settings saved");
        settings(host);
      } catch (ex) {
        err.append(formError(ex.message));
      }
    });
  });
  host.append(section("Budgets", form));
}
