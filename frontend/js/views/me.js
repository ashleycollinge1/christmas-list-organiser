import { api } from "../api.js";
import { h, icon, reveal, clear, skeletonLines, toast, confirmDialog } from "../dom.js";
import { money } from "../format.js";
import { openPersonSheet } from "../components.js";
import { actionSheet } from "../sheet.js";
import { openWishSheet, wishRow, wishPrice, summaryText, shareWishes, occasionChoices } from "../wishes.js";
import { searchBox, searchSummary, matches, createSelection, selectRow, selectToggle, selectBar } from "../listtools.js";

export async function render(main, ctx) {
  const focus = Number(ctx.query.get("o")) || null;
  const page = h("div.page.me");
  page.append(h("div.loading", { "aria-label": "Loading" }, skeletonLines(["w-40"]), skeletonLines(), skeletonLines()));
  main.append(page);

  const search = { query: "" };
  const sel = createSelection();
  let data;
  let mePerson;
  let archivedOpen = false;

  async function load() {
    const [wishes, { people }] = await Promise.all([api("/api/wishes"), api("/api/people")]);
    data = wishes;
    mePerson = people.find((p) => p.kind === "me") || null;
    draw();
  }

  const hit = (w) => matches(search.query, w.description, w.notes, w.link, w.occasion?.name);

  function row(w) {
    if (!sel.active) return wishRow(w, load);
    return selectRow(sel, w.id, [
      h("span.wish-title", w.description),
      h("span.gift-meta", wishPrice(w) && h("span.meta-price", wishPrice(w)), w.archived && h("span", "Archived")),
    ], { className: `wish${w.archived ? ".is-archived" : ""}`, onChange: draw });
  }

  function draw() {
    const name = data.me?.name || ctx.session.user.name;
    const searching = Boolean(search.query.trim());
    const active = data.wishes.filter((w) => !w.archived && hit(w));
    const archived = data.wishes.filter((w) => w.archived && hit(w));
    clear(page);

    // Anytime first, then occasions (active before archived).
    const groups = new Map([["anytime", { occasion: null, wishes: [] }]]);
    for (const w of active) {
      const key = w.occasion ? `o${w.occasion.id}` : "anytime";
      if (!groups.has(key)) groups.set(key, { occasion: w.occasion, wishes: [] });
      groups.get(key).wishes.push(w);
    }
    const ordered = [...groups.values()].sort((a, b) =>
      (a.occasion ? (a.occasion.is_archived ? 2 : 1) : 0) - (b.occasion ? (b.occasion.is_archived ? 2 : 1) : 0));

    const allActive = data.wishes.filter((w) => !w.archived);
    const head = h("header.page-head",
      h("a.back.no-print", { href: "#/people" }, icon("back"), "People"),
      h("div.title-row",
        h("div", h("p.eyebrow", name), h("h1.page-title", "My wish list")),
        h("div.row.row-tight.no-print",
          h("button.btn.btn-icon", { type: "button", "aria-label": "Share my wish list", onclick: () => shareWishes(name, null, allActive, data.me?.notes) }, icon("share")),
          h("button.btn.btn-icon", { type: "button", "aria-label": "Print", onclick: () => window.print() }, icon("printer")))),
      h("p.page-sub", h("strong", summaryText(data.totals))));

    const about = h("section.notes-card",
      h("div.wish-card-head",
        h("p.label", icon("note"), "Sizes & notes"),
        mePerson && h("button.btn.btn-sm.no-print", { type: "button", onclick: () => openPersonSheet({ person: mePerson, onSaved: load }) }, "Edit")),
      h("p.notes", data.me?.notes || "Add your sizes and favourite things, so they're included when you share."));
    if (!mePerson) about.hidden = true;

    const parts = [head, about];
    if (!data.wishes.length) {
      parts.push(h("div.empty",
        h("span.empty-star", { "aria-hidden": "true" }),
        h("h3", "What would you like?"),
        h("p.muted", "Add ideas for any time, or for a birthday or Christmas. On your iPhone you can add straight from Safari's Share button: see Account."),
        h("button.btn.btn-primary", { type: "button", onclick: () => openWishSheet({ onSaved: load }) }, icon("plus"), "Add your first wish")));
    } else {
      parts.push(h("div.no-print",
        searchBox(search, { placeholder: "Search my wishes, including archived", label: "Search wishes", onInput: draw }),
        h("div.list-tools", h("span"), selectToggle(sel, { onChange: draw })),
        searchSummary(search, active.length + archived.length, data.wishes.length, "wish", "wishes")));
    }
    for (const g of ordered) {
      if (!g.wishes.length && (searching || !allActive.length || g.occasion)) continue;
      const title = g.occasion ? g.occasion.name : "Anytime";
      const total = g.wishes.reduce((n, w) => n + (w.line_total_pence || 0), 0);
      parts.push(h(`section.section.wish-group${g.occasion ? `#wo-${g.occasion.id}` : "#wo-anytime"}`,
        h("div.group-head",
          h("h2.group-title", title, g.occasion?.is_archived && " (archived)"),
          h("span.row.row-tight",
            h("span.group-total", g.wishes.length ? money(total) : ""),
            g.wishes.length > 0 && !sel.active && h("button.btn.btn-icon.btn-ghost.no-print", {
              type: "button", "aria-label": `Share ${title} list`,
              onclick: () => shareWishes(name, g.occasion ? title : null, g.wishes, data.me?.notes),
            }, icon("share")))),
        g.wishes.length
          ? h("ul.wish-list", g.wishes.map(row))
          : h("p.muted.small", "Ideas that aren't for anything in particular go here.")));
    }
    if (archived.length) {
      const det = h("details.archived.no-print", { open: archivedOpen || searching || sel.active },
        h("summary", icon("archive"), `Archived ideas (${archived.length})`, icon("down")),
        h("p.muted.small", "Things you've had, or gone off. Open one to restore it if you're stuck for ideas."),
        h("ul.wish-list", archived.map(row)));
      det.addEventListener("toggle", () => { archivedOpen = det.open; });
      parts.push(det);
    }
    reveal(parts);
    page.append(...parts);
    // Animate the first draw only, not every keystroke or tick.
    queueMicrotask(() => page.classList.add("settled"));

    if (sel.active) {
      const chosen = data.wishes.filter((w) => sel.ids.has(w.id));
      const allArchived = chosen.length > 0 && chosen.every((w) => w.archived);
      page.append(selectBar(sel, [...active, ...archived].map((w) => w.id), [
        { label: "Move…", run: bulk(moveTo) },
        { label: allArchived ? "Restore" : "Archive", run: bulk((ids) => post(ids, allArchived ? "restore" : "archive")) },
        { label: "Delete", danger: true, run: bulk(remove) },
      ], { onChange: draw }));
    } else {
      page.append(h("div.fab-wrap.no-print", h("button.btn.btn-primary.fab", {
        type: "button",
        onclick: () => openWishSheet({ occasionId: focus, onSaved: load }),
      }, icon("plus"), "Add a wish")));
    }
  }

  const plural = (n) => `${n} wish${n === 1 ? "" : "es"}`;

  function bulk(fn) {
    return async (ids) => {
      try {
        if (await fn(ids)) { sel.active = false; sel.ids.clear(); await load(); }
      } catch (err) { toast(err.message, "error"); }
    };
  }

  async function post(ids, action, extra = {}) {
    await api("/api/wishes/bulk", { method: "POST", body: { ids, action, ...extra } });
    const done = { archive: "archived", restore: "restored", delete: "deleted" }[action];
    if (done) toast(`${plural(ids.length)} ${done}`);
    return true;
  }

  async function moveTo(ids) {
    const occasions = (await occasionChoices({ fresh: true })).filter((o) => !o.is_archived);
    const target = await actionSheet({
      title: `Move ${plural(ids.length)}`, message: "To which list?",
      actions: [{ label: "Anytime", value: { id: null, name: "Anytime" } }, ...occasions.map((o) => ({ label: o.name, value: o }))],
    });
    if (!target) return false;
    await post(ids, "move", { occasion_id: target.id });
    toast(`Moved to ${target.name}`);
    return true;
  }

  async function remove(ids) {
    if (!(await confirmDialog(`Delete ${plural(ids.length)}?`, "They'll be removed for good. Archive keeps them as ideas."))) return false;
    return post(ids, "delete");
  }

  await load();
  if (focus) document.getElementById(`wo-${focus}`)?.scrollIntoView({ block: "start" });
}
