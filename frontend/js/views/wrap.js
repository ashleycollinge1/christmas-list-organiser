import { api } from "../api.js";
import { h, icon, reveal, clear, skeletonLines, toast } from "../dom.js";
import { STATUS_LABEL } from "../format.js";
import { archivedBanner, setArchived } from "../components.js";

const HIDE_KEY = "wrap.hideDone";
const LAST_KEY = "wrap.occasion";
// Only gifts you actually have: delivered onwards. Ordered or reordered ones are still on their way.
const WRAPPABLE = new Set(["delivered", "wrapped", "given"]);
const DONE = new Set(["wrapped", "given"]);

export async function render(main, ctx) {
  const page = h("div.page.wrap");
  page.append(h("div.loading", { "aria-label": "Loading" }, skeletonLines(["w-40"]), skeletonLines(), skeletonLines()));
  main.append(page);

  let data;
  let hideDone = localStorage.getItem(HIDE_KEY) === "1";

  const { occasions } = await api("/api/occasions");
  const active = occasions.filter((o) => !o.is_archived);
  const wanted = Number(ctx.query.get("o") || localStorage.getItem(LAST_KEY));
  const chosen = occasions.find((o) => o.id === wanted) || active[0];
  if (!chosen) {
    clear(page).append(h("header.page-head", h("h1.page-title", "Wrapping")), h("div.empty",
      h("span.empty-star", { "aria-hidden": "true" }),
      h("h3", "No active occasions"),
      h("p.muted", "Create or unarchive an occasion from Home.")));
    return;
  }
  localStorage.setItem(LAST_KEY, String(chosen.id));

  async function load() {
    data = await api(`/api/occasions/${chosen.id}/overview`);
    ctx.setOccasion(data.occasion);
    draw();
  }

  function picker() {
    const list = active.some((o) => o.id === chosen.id) ? active : [chosen, ...active];
    if (list.length < 2) return null;
    return h("nav.jump.no-print", { "aria-label": "Occasion" }, list.map((o) =>
      h("a.chip", { href: `#/wrap?o=${o.id}`, "aria-current": o.id === chosen.id ? "page" : null }, o.name)));
  }

  function draw() {
    clear(page);
    const ro = data.read_only;
    const people = [];
    let total = 0;
    let done = 0;
    let notHere = 0;
    for (const g of data.groups) {
      for (const r of g.recipients) {
        const gifts = r.gifts.filter((x) => WRAPPABLE.has(x.status));
        notHere += r.gifts.filter((x) => ["ordered", "reorder"].includes(x.status)).length;
        if (!gifts.length) continue;
        total += gifts.length;
        done += gifts.filter((x) => DONE.has(x.status)).length;
        people.push({ r, gifts });
      }
    }

    const pct = total ? Math.round((done / total) * 100) : 0;
    const head = h("header.page-head",
      h("p.eyebrow", data.occasion.name),
      h("div.title-row",
        h("h1.page-title", "Wrapping"),
        h("button.btn.btn-icon.no-print", { type: "button", "aria-label": "Print checklist", onclick: () => window.print() }, icon("printer"))),
      total > 0 && h("div.wrap-progress",
        h("p.wrap-count", h("strong", String(done)), ` of ${total} wrapped`),
        h("div.meter.meter-lg.state-on", { role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(total), "aria-valuenow": String(done), "aria-label": "Wrapped" },
          h("span.meter-spent", { style: { width: `${pct}%` } }))),
      notHere > 0 && h("p.muted.small", `${notHere} gift${notHere === 1 ? " is" : "s are"} ordered but not delivered yet, so ${notHere === 1 ? "isn't" : "aren't"} listed.`));

    const toggle = total > 0 && h("label.switch-row.no-print",
      h("input", { type: "checkbox", role: "switch", checked: hideDone, onchange: (e) => {
        hideDone = e.target.checked;
        localStorage.setItem(HIDE_KEY, hideDone ? "1" : "0");
        draw();
      } }),
      h("span.switch", { "aria-hidden": "true" }),
      h("span", "Hide wrapped"));

    const banner = ro && archivedBanner(data.occasion, async () => { await setArchived(data.occasion, false); load(); });
    const parts = [banner, head, picker(), toggle].filter(Boolean);

    if (!total) {
      parts.push(h("div.empty",
        h("span.empty-star", { "aria-hidden": "true" }),
        h("h3", "Nothing to wrap yet"),
        h("p.muted", "Gifts appear here once they're marked Delivered.")));
    } else {
      let shown = 0;
      for (const { r, gifts } of people) {
        const visible = hideDone ? gifts.filter((g) => !DONE.has(g.status)) : gifts;
        if (!visible.length) continue;
        shown += visible.length;
        const doneHere = gifts.filter((g) => DONE.has(g.status)).length;
        parts.push(h("section.wrap-group", { "aria-labelledby": `wg-${r.id}` },
          h("div.group-head",
            h("h2.group-title#" + `wg-${r.id}`, r.name),
            h("span.group-total", `${doneHere}/${gifts.length}`)),
          h("ul.check-list", visible.map((g) => wrapRow(g, ro)))));
      }
      if (!shown) {
        parts.push(h("div.empty",
          h("span.empty-star", { "aria-hidden": "true" }),
          h("h3", "All wrapped"),
          h("p.muted", "Every delivered gift is wrapped. Time for a mince pie.")));
      }
    }
    reveal(parts);
    page.append(...parts);
  }

  function wrapRow(g, ro) {
    const isDone = DONE.has(g.status);
    const given = g.status === "given";
    const input = h("input", {
      type: "checkbox", checked: isDone, disabled: ro || given, "aria-describedby": `wd-${g.id}`,
      onchange: async (e) => {
        const status = e.target.checked ? "wrapped" : "delivered";
        const row = e.target.closest(".check-item");
        row.classList.toggle("is-done", e.target.checked);
        try {
          await api(`/api/gifts/${g.id}`, { method: "PATCH", body: { status } });
          g.status = status;
          if (hideDone && e.target.checked) setTimeout(() => load().catch(() => {}), 600);
          else await load();
        } catch (err) {
          e.target.checked = !e.target.checked;
          row.classList.toggle("is-done", e.target.checked);
          toast(err.message, "error");
        }
      },
    });
    return h(`li.check-item${isDone ? ".is-done" : ""}`,
      h("label.check-row.check-row-lg",
        input,
        h("span.check-box", { "aria-hidden": "true" }, icon("check")),
        h("span.check-text",
          h("span.check-title", g.quantity > 1 ? `${g.description} ×${g.quantity}` : g.description),
          h(`span.check-sub#wd-${g.id}`,
            g.hiding_place ? h("span.hidden-at", icon("pin"), g.hiding_place) : null,
            given && h("span", STATUS_LABEL.given)))));
  }

  await load();
}
