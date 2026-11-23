import { api } from "../api.js";
import { h, icon, reveal, clear, skeletonLines } from "../dom.js";
import { money } from "../format.js";
import {
  meter, budgetLine, statusPill, changeStatus, giftMeta, trackingChip, deliveryChip, linkChip, hidingChip,
  openGiftSheet, openRecipientSheet, archivedBanner,
} from "../components.js";

export async function render(main, ctx) {
  const id = Number(ctx.params[0]);
  const page = h("div.page.recipient");
  page.append(h("div.loading", { "aria-label": "Loading" }, skeletonLines(["w-40"]), h("span.skeleton.skeleton-hero"), skeletonLines()));
  main.append(page);

  let r;
  let season;
  async function load() {
    const res = await api(`/api/recipients/${id}`);
    r = res.recipient;
    season = res.season;
    ctx.setSeasonTag(season);
    draw();
  }

  function draw() {
    clear(page);
    const ro = r.read_only;
    const t = r.totals;
    const back = season.is_archived ? `#/?season=${season.id}` : "#/";

    const head = h("header.page-head",
      h("a.back", { href: back }, icon("back"), "Overview"),
      h("div.title-row",
        h("h1.page-title", r.name),
        !ro && h("button.btn.btn-icon", {
          type: "button", "aria-label": `Edit ${r.name}`,
          onclick: () => openRecipientSheet({
            recipient: r, me: ctx.session.user,
            onSaved: load,
            onDeleted: () => ctx.navigate("/"),
          }),
        }, icon("pencil"))),
      h("p.page-sub",
        r.category && h("span.tag", r.category.name),
        !r.is_owner && h("span.muted", `Shared by ${r.owner.name}`),
        r.is_owner && r.shared_with.length > 0 && h("span.muted", h("span.inline-icon", icon("users")), `Shared with ${r.shared_with.map((p) => p.name).join(", ")}`)));

    const budget = h("section.budget-card", { "aria-label": "Budget" },
      h("div.budget-figures",
        h("div", h("p.label", "Spent"), h("p.figure", money(t.spent_pence))),
        h("div", h("p.label", "Budget"), h("p.figure.figure-muted", t.budget_pence != null ? money(t.budget_pence) : "—")),
        h("div", h("p.label", "With ideas"), h(`p.figure.figure-muted${t.planned_state === "over" ? ".is-over" : ""}`, money(t.planned_pence)))),
      meter(t, { large: true }),
      h("p.budget-state", budgetLine(t),
        t.unpriced > 0 && h("span.muted", ` · ${t.unpriced} without a price`)));

    const notes = r.notes && h("section.notes-card", h("p.label", icon("note"), "Notes"), h("p.notes", r.notes));

    const list = h("section.section", { "aria-labelledby": "gifts-h" },
      h("h2.section-title#gifts-h", "Gifts", t.gift_count > 0 && h("span.count-badge", String(t.gift_count))));
    if (!r.gifts.length) {
      list.append(h("div.empty",
        h("span.empty-star", { "aria-hidden": "true" }),
        h("h3", ro ? "No gifts" : `Nothing for ${r.name} yet`),
        !ro && h("p.muted", "Add ideas now and mark them ordered when you buy them.")));
    } else {
      list.append(h("ul.gift-list", r.gifts.map((g) => giftCard(g, ro))));
    }

    const parts = [season.is_archived && archivedBanner(season, ctx.navigate), head, budget, notes, list].filter(Boolean);
    reveal(parts);
    page.append(...parts);

    if (!ro) {
      page.append(h("div.fab-wrap", h("button.btn.btn-primary.fab", {
        type: "button",
        onclick: () => openGiftSheet({ recipient: r, onSaved: load }),
      }, icon("plus"), "Add gift")));
    }
  }

  function giftCard(g, ro) {
    const chips = [deliveryChip(g), trackingChip(g), hidingChip(g), linkChip(g)].filter(Boolean);
    const buyer = r.shared_with.length > 0 && g.buyer && h("span.buyer", g.buyer.id === ctx.session.user.id ? "You're buying" : `${g.buyer.name} is buying`);
    return h(`li.gift.status-${g.status}`,
      h("button.gift-main", {
        type: "button",
        "aria-label": `${g.description}. ${ro ? "View" : "Edit"} details`,
        onclick: () => openGiftSheet({ recipient: r, gift: g, readOnly: ro, onSaved: load }),
      },
      h("span.gift-title", g.description),
      giftMeta(g),
      buyer,
      g.notes && h("span.gift-notes", g.notes)),
      statusPill(g, { readOnly: ro, onChange: (s, prev) => changeStatus(g, s, prev, load) }),
      chips.length > 0 && h("div.chips.gift-chips", chips));
  }

  await load();
}
