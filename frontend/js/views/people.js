import { api } from "../api.js";
import { h, icon, reveal, clear, skeletonLines } from "../dom.js";
import { openPersonSheet } from "../components.js";

export async function render(main, ctx) {
  const page = h("div.page.people");
  page.append(h("div.loading", { "aria-label": "Loading" }, skeletonLines(["w-40"]), skeletonLines(), skeletonLines()));
  main.append(page);

  async function load() {
    const { people: everyone } = await api("/api/people");
    const me = everyone.find((p) => p.kind === "me");
    const people = everyone.filter((p) => p.kind !== "me");
    clear(page);
    const head = h("header.page-head",
      h("p.eyebrow", "Gift List"),
      h("h1.page-title", "People"),
      h("p.page-sub.muted", "Everyone you buy for. Notes and categories are shared across all their occasions."));
    const meCard = h("a.person.me-card", { href: "#/me" },
      h("div.person-top",
        h("span.person-name", icon("gift"), me ? "My wish list" : "Start my wish list"),
        icon("chevron")),
      h("span.muted.small", me ? `${me.name}: things you'd like, for any time or a particular occasion` : "Keep track of things you'd like, and share them when people ask."));
    const parts = [head, meCard];
    if (!people.length) {
      parts.push(h("div.empty",
        h("span.empty-star", { "aria-hidden": "true" }),
        h("h3", "No one yet"),
        h("p.muted", "Add people here, or straight from an occasion.")));
    } else {
      parts.push(h("ul.person-list", people.map((p) => {
        const active = p.entries.filter((e) => !e.occasion.is_archived);
        return h("li", h("button.person.person-btn", {
          type: "button",
          onclick: () => openPersonSheet({ person: p, onSaved: load }),
        },
        h("div.person-top",
          h("span.person-name", p.name),
          p.category && h("span.tag", p.category.name)),
        p.notes && h("span.gift-notes", p.notes),
        h("span.person-occasions.muted.small",
          active.length ? active.map((e) => e.occasion.name).join(" · ") : p.entries.length ? "Only in archived occasions" : "Not in any occasion")));
      })));
    }
    reveal(parts);
    page.append(...parts);
    page.append(h("div.fab-wrap", h("button.btn.btn-primary.fab", {
      type: "button",
      onclick: () => openPersonSheet({
        canBeMe: !me,
        me: ctx.session.user,
        onSaved: (p) => (p?.kind === "me" ? ctx.navigate("/me") : load()),
      }),
    }, icon("plus"), "New person")));
  }

  await load();
}
