import { api } from "../api.js";
import { h, icon, reveal, clear, skeletonLines } from "../dom.js";
import { money, KIND_LABEL, occasionWhen } from "../format.js";
import { meter, budgetLine, statusDots, openNewOccasionSheet } from "../components.js";
import { summaryText } from "../wishes.js";

export async function render(main, ctx) {
  const page = h("div.page.home");
  page.append(h("div.loading", { "aria-label": "Loading" }, skeletonLines(["w-40"]), h("span.skeleton.skeleton-hero"), h("span.skeleton.skeleton-hero")));
  main.append(page);

  const { occasions } = await api("/api/occasions");
  const active = occasions.filter((o) => !o.is_archived);
  const archived = occasions.filter((o) => o.is_archived);
  clear(page);

  const head = h("header.page-head", h("p.eyebrow", "Gift List"), h("h1.page-title", "Occasions"));
  const parts = [head];

  if (!active.length) {
    parts.push(h("div.empty",
      h("span.empty-star", { "aria-hidden": "true" }),
      h("h3", "Nothing on the go"),
      h("p.muted", archived.length ? "Every occasion is archived. Start a new one, or unarchive an old one." : "Create a Christmas or a birthday to start planning.")));
  } else {
    parts.push(h("ul.occasion-list", active.map(card)));
  }

  if (archived.length) {
    parts.push(h("details.archived",
      h("summary", icon("archive"), `Archived (${archived.length})`, icon("down")),
      h("ul.admin-list", archived.map((o) => h("li", h("a.admin-row.archived-row", { href: `#/o/${o.id}` },
        h("div.admin-main",
          h("p.admin-title", o.name),
          h("p.admin-sub", KIND_LABEL[o.kind], o.totals.spent_pence > 0 && `· ${money(o.totals.spent_pence)} spent`)),
        icon("chevron")))))));
  }
  reveal(parts);
  page.append(...parts);

  page.append(h("div.fab-wrap", h("button.btn.btn-primary.fab", {
    type: "button",
    onclick: () => openNewOccasionSheet({ me: ctx.session.user, onSaved: (o) => ctx.navigate(`/o/${o.id}`) }),
  }, icon("plus"), "New occasion")));
}

function card(o) {
  const t = o.totals;
  const when = occasionWhen(o.date);
  // Just for you: show your wish list instead of an empty budget.
  if (o.people === 0 && o.my_wishes?.count > 0) {
    return h("li", h(`a.occasion-card.kind-${o.kind}`, { href: `#/o/${o.id}` },
      h("div.occasion-top",
        h("span.kind-tag", KIND_LABEL[o.kind]),
        when && h(`span.when${when.past ? ".is-past" : ""}`, { title: when.date }, when.when)),
      h("h2.occasion-name", o.name),
      h("div.person-top", h("span.person-money", "My wish list"), h("span.muted.small", summaryText(o.my_wishes)))));
  }
  return h("li", h(`a.occasion-card.kind-${o.kind}`, { href: `#/o/${o.id}` },
    h("div.occasion-top",
      h("span.kind-tag", KIND_LABEL[o.kind]),
      when && h(`span.when${when.past ? ".is-past" : ""}`, { title: when.date }, when.when)),
    h("h2.occasion-name", o.name),
    h("div.person-top",
      h("span.person-money", money(t.spent_pence), t.budget_pence != null && h("span.muted", ` / ${money(t.budget_pence)}`)),
      h("span.muted.small", `${o.people} ${o.people === 1 ? "person" : "people"}`)),
    meter(t),
    h("div.person-bottom", budgetLine(t), statusDots(t.counts))));
}
