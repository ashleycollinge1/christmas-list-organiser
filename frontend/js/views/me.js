import { api } from "../api.js";
import { h, icon, reveal, clear, skeletonLines } from "../dom.js";
import { money } from "../format.js";
import { openPersonSheet } from "../components.js";
import { openWishSheet, wishRow, summaryText, shareWishes } from "../wishes.js";

export async function render(main, ctx) {
  const focus = Number(ctx.query.get("o")) || null;
  const page = h("div.page.me");
  page.append(h("div.loading", { "aria-label": "Loading" }, skeletonLines(["w-40"]), skeletonLines(), skeletonLines()));
  main.append(page);

  async function load() {
    const [data, { people }] = await Promise.all([api("/api/wishes"), api("/api/people")]);
    const mePerson = people.find((p) => p.kind === "me") || null;
    const name = data.me?.name || ctx.session.user.name;
    const active = data.wishes.filter((w) => !w.archived);
    const archived = data.wishes.filter((w) => w.archived);
    clear(page);

    // Group: Anytime first, then occasions (active before archived, by name order of appearance).
    const groups = new Map([["anytime", { occasion: null, wishes: [] }]]);
    for (const w of active) {
      const key = w.occasion ? `o${w.occasion.id}` : "anytime";
      if (!groups.has(key)) groups.set(key, { occasion: w.occasion, wishes: [] });
      groups.get(key).wishes.push(w);
    }
    const ordered = [...groups.values()].sort((a, b) =>
      (a.occasion ? (a.occasion.is_archived ? 2 : 1) : 0) - (b.occasion ? (b.occasion.is_archived ? 2 : 1) : 0));

    const head = h("header.page-head",
      h("a.back.no-print", { href: "#/people" }, icon("back"), "People"),
      h("div.title-row",
        h("div", h("p.eyebrow", name), h("h1.page-title", "My wish list")),
        h("div.row.row-tight.no-print",
          h("button.btn.btn-icon", { type: "button", "aria-label": "Share my wish list", onclick: () => shareWishes(name, null, active, data.me?.notes) }, icon("share")),
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
    }
    for (const g of ordered) {
      if (!g.occasion && !g.wishes.length && !active.length) continue;
      const title = g.occasion ? g.occasion.name : "Anytime";
      const total = g.wishes.reduce((n, w) => n + (w.line_total_pence || 0), 0);
      parts.push(h(`section.section.wish-group${g.occasion ? `#wo-${g.occasion.id}` : "#wo-anytime"}`,
        h("div.group-head",
          h("h2.group-title", title, g.occasion?.is_archived && " (archived)"),
          h("span.row.row-tight",
            h("span.group-total", g.wishes.length ? money(total) : ""),
            g.wishes.length > 0 && h("button.btn.btn-icon.btn-ghost.no-print", {
              type: "button", "aria-label": `Share ${title} list`,
              onclick: () => shareWishes(name, g.occasion ? title : null, g.wishes, data.me?.notes),
            }, icon("share")))),
        g.wishes.length
          ? h("ul.wish-list", g.wishes.map((w) => wishRow(w, load)))
          : h("p.muted.small", g.occasion ? "Nothing here." : "Ideas that aren't for anything in particular go here.")));
    }
    if (archived.length) {
      parts.push(h("details.archived.no-print",
        h("summary", icon("archive"), `Archived ideas (${archived.length})`, icon("down")),
        h("p.muted.small", "Things you've had, or gone off. Open one to restore it if you're stuck for ideas."),
        h("ul.wish-list", archived.map((w) => wishRow(w, load)))));
    }
    reveal(parts);
    page.append(...parts);
    page.append(h("div.fab-wrap.no-print", h("button.btn.btn-primary.fab", {
      type: "button",
      onclick: () => openWishSheet({ occasionId: focus, onSaved: load }),
    }, icon("plus"), "Add a wish")));

    if (focus) document.getElementById(`wo-${focus}`)?.scrollIntoView({ block: "start" });
  }

  await load();
}
