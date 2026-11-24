import { api } from "../api.js";
import { h, icon, reveal, clear, skeletonLines } from "../dom.js";
import { money, KIND_LABEL, occasionWhen } from "../format.js";
import {
  meter, budgetLine, statusDots, statusPill, changeStatus, giftMeta, trackingChip, deliveryChip,
  openAddPersonSheet, openGiftSheet, archivedBanner, occasionMenu, setArchived,
} from "../components.js";
import { myWishesCard } from "../wishes.js";

export async function render(main, ctx) {
  const occasionId = Number(ctx.params[0]);
  const page = h("div.page.overview");
  page.append(h("div.loading", { "aria-label": "Loading" }, h("span.skeleton.skeleton-hero"), skeletonLines(), skeletonLines(["w-85", "w-60"])));
  main.append(page);

  let data;
  async function load() {
    data = await api(`/api/occasions/${occasionId}/overview`);
    ctx.setOccasion(data.occasion);
    draw();
  }

  function findRecipient(id) {
    for (const g of data.groups) for (const r of g.recipients) if (r.id === id) return r;
    return null;
  }

  function draw() {
    clear(page);
    const ro = data.read_only;
    const t = data.totals;
    const people = data.groups.reduce((n, g) => n + g.recipients.length, 0);

    const o = data.occasion;
    const when = occasionWhen(o.date);
    const head = h("header.page-head",
      h("a.back", { href: "#/" }, icon("back"), "Home"),
      h("div.title-row",
        h("div",
          h("p.eyebrow", KIND_LABEL[o.kind], when && ` · ${when.date} · ${when.when}`),
          h("h1.page-title", o.name)),
        o.can_manage && h("button.btn.btn-icon", {
          type: "button", "aria-label": `Manage ${o.name}`,
          onclick: () => occasionMenu(data, { onChanged: () => load(), onDeleted: () => ctx.navigate("/") }),
        }, icon("more"))));

    const hero = h("section.hero",
      h("p.hero-figure", h("span.hero-amount", money(t.spent_pence)),
        t.budget_pence != null && h("span.hero-of", `of ${money(t.budget_pence)} budget`)),
      meter(t, { large: true }),
      h("p.hero-sub", budgetLine(t),
        t.planned_pence !== t.spent_pence && h("span.muted", ` · ${money(t.planned_pence)} with ideas`)),
      t.gift_count > 0 && h("div.hero-counts", statusDots(t.counts)));

    const jump = (people > 0) && h("nav.jump", { "aria-label": "Sections" },
      h("a.chip", { href: "#people", onclick: jumpTo("people") }, icon("users"), `${people} ${people === 1 ? "person" : "people"}`),
      data.awaiting_delivery.length > 0 && h("a.chip", { href: "#awaiting", onclick: jumpTo("awaiting") }, icon("truck"), `${data.awaiting_delivery.length} awaiting`),
      data.to_order.length > 0 && h("a.chip", { href: "#to-order", onclick: jumpTo("to-order") }, icon("gift"), `${data.to_order.length} to order`));

    const sections = [
      ro && archivedBanner(o, async () => { await setArchived(o, false); load(); }),
      head,
      hero,
      data.my_wishes && myWishesCard(o, data.my_wishes, { onChanged: () => load() }),
      jump,
      peopleSection(ro),
      data.awaiting_delivery.length > 0 && awaitingSection(ro),
      data.to_order.length > 0 && toOrderSection(ro),
    ].filter(Boolean);
    reveal(sections);
    page.append(...sections);

    if (!ro) {
      page.append(h("div.fab-wrap", h("button.btn.btn-primary.fab", {
        type: "button",
        onclick: () => openAddPersonSheet({
          occasion: data.occasion,
          me: ctx.session.user,
          onSaved: (r) => ctx.navigate(`/r/${r.id}`),
        }),
      }, icon("plus"), "Add person")));
    }
  }

  function jumpTo(id) {
    return (e) => {
      e.preventDefault();
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }

  function peopleSection(ro) {
    const sec = h("section.section#people", { "aria-labelledby": "people-h" },
      h("h2.section-title#people-h", "People"));
    if (!data.groups.length) {
      sec.append(h("div.empty",
        h("span.empty-star", { "aria-hidden": "true" }),
        h("h3", ro ? "Nobody here" : "Who are you buying for?"),
        h("p.muted", ro ? "This archived occasion has nobody in it." : "Add each person with a budget, then list their gifts.")));
      return sec;
    }
    for (const g of data.groups) {
      const block = h("div.group");
      if (data.groups.length > 1 || g.category) {
        block.append(h("div.group-head",
          h("h3.group-title", g.category ? g.category.name : "Uncategorised"),
          h("span.group-total", money(g.totals.spent_pence), g.totals.budget_pence != null && h("span.muted", ` / ${money(g.totals.budget_pence)}`))));
      }
      block.append(h("ul.person-list", g.recipients.map(personRow)));
      sec.append(block);
    }
    return sec;
  }

  function personRow(r) {
    const t = r.totals;
    return h("li", h("a.person", { href: `#/r/${r.id}` },
      h("div.person-top",
        h("span.person-name", r.name),
        h("span.person-money", money(t.spent_pence), t.budget_pence != null && h("span.muted", ` / ${money(t.budget_pence)}`))),
      meter(t),
      h("div.person-bottom",
        budgetLine(t),
        statusDots(t.counts) || h("span.muted.small", "No gifts yet"),
        (r.shared_with.length > 0 || !r.is_owner) && h("span.shared-badge", { title: "Shared" }, icon("users"))),
    ));
  }

  function giftRow(g, ro, extra) {
    const r = findRecipient(g.recipient_id);
    // Chips (copy tracking) are buttons themselves, so they sit outside the row button.
    return h("li.mini-gift",
      h("button.mini-main", {
        type: "button",
        onclick: () => openGiftSheet({ recipient: r, gift: g, readOnly: ro, onSaved: load }),
      },
      h("span.mini-title", g.description),
      giftMeta(g, { showRecipient: true })),
      statusPill(g, { readOnly: ro, onChange: (s, prev) => changeStatus(g, s, prev, load) }),
      extra?.length > 0 && h("div.chips.mini-chips", extra));
  }

  function awaitingSection(ro) {
    return h("section.section#awaiting", { "aria-labelledby": "awaiting-h" },
      h("h2.section-title#awaiting-h", "Awaiting delivery"),
      h("ul.mini-list", data.awaiting_delivery.map((g) => giftRow(g, ro, [deliveryChip(g), trackingChip(g)].filter(Boolean)))));
  }

  function toOrderSection(ro) {
    return h("section.section#to-order", { "aria-labelledby": "to-order-h" },
      h("h2.section-title#to-order-h", "Still to order"),
      h("ul.mini-list", data.to_order.map((g) => giftRow(g, ro))));
  }

  await load();
}
