// The form the iOS Shortcut opens: /share?url=… redirects here with the shared link.

import { api } from "../api.js";
import { h, icon, reveal, clear, formError, busy, toast } from "../dom.js";
import { money, moneyInput } from "../format.js";
import { wishFields, readWish, occasionChoices } from "../wishes.js";

export async function render(main, ctx) {
  const shared = ctx.query.get("url") || "";
  const page = h("div.page.add-page");
  main.append(page);
  const occasions = await occasionChoices({ fresh: true });
  showForm();

  function showForm() {
    clear(page);
    const status = h("p.reading", { "aria-live": "polite" });
    const err = h("div", { "aria-live": "assertive" });
    const save = h("button.btn.btn-primary.btn-block.btn-lg", { type: "submit", dataset: { busyLabel: "Adding…" } }, icon("plus"), "Add to my wish list");
    const form = h("form.form", { novalidate: true, autocomplete: "off" }, err, ...wishFields({ link: shared, priority: 2, quantity: 1 }, occasions), save);
    // Show the link first: it's what was shared.
    const linkField = form.link.closest(".field");
    form.prepend(linkField);
    linkField.after(status);

    const head = h("header.page-head", h("p.eyebrow", "Gift List"), h("h1.page-title", "Add a wish"));
    reveal(head, form);
    page.append(head, form);

    const touched = new Set();
    form.description.addEventListener("input", () => touched.add("description"));
    form.price.addEventListener("input", () => touched.add("price"));

    async function read(url) {
      if (!url) return;
      status.className = "reading is-busy";
      status.replaceChildren(h("span.spinner"), "Reading the page…");
      form.description.placeholder = "Reading the page…";
      try {
        const res = await api(`/api/wishes/preview?url=${encodeURIComponent(url)}`);
        const p = res.preview;
        if (p.title && !touched.has("description")) form.description.value = p.title;
        if (p.price_pence != null && !touched.has("price")) form.price.value = moneyInput(p.price_pence);
        if (res.error) {
          status.className = "reading is-warn";
          status.replaceChildren(icon("alert"), res.guessed
            ? `${res.error} The name was guessed from the link, so check it.`
            : `${res.error} Fill in the details yourself.`);
        } else {
          status.className = "reading is-ok";
          status.replaceChildren(icon("check"), [p.site, p.price_pence != null && money(p.price_pence)].filter(Boolean).join(" · ") || "Details filled in");
        }
      } catch (ex) {
        status.className = "reading is-warn";
        status.replaceChildren(icon("alert"), ex.message);
      } finally {
        form.description.placeholder = "e.g. Noise-cancelling headphones";
      }
    }
    // Re-read when a different link is pasted in.
    let lastRead = shared;
    form.link.addEventListener("change", () => {
      const v = form.link.value.trim();
      if (v && v !== lastRead) { lastRead = v; read(v); }
    });
    read(shared);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      err.replaceChildren();
      await busy(save, async () => {
        try {
          const res = await api("/api/wishes", { method: "POST", body: readWish(form) });
          showDone(res.wish);
        } catch (ex) {
          err.append(formError(ex.message));
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });
  }

  function showDone(wish) {
    clear(page);
    const where = wish.occasion ? wish.occasion.name : "Anytime";
    const hint = h("p.muted.small.center", "You can close this window now.");
    const card = h("section.done-card",
      h("span.done-tick", { "aria-hidden": "true" }, icon("check")),
      h("h1.page-title", "Added"),
      h("p.lede.center", h("strong", wish.description), ` is on your ${where} list.`),
      h("div.stack",
        h("button.btn.btn-primary.btn-block", {
          type: "button",
          onclick: () => {
            window.close();
            // Only windows opened by a script can close themselves; otherwise point at the Done button.
            setTimeout(() => { hint.textContent = "Tap Done at the top of the screen to close."; hint.classList.add("is-warn"); }, 300);
          },
        }, "Done"),
        h("a.btn.btn-block", { href: "#/me" }, "View my wish list"),
        h("button.btn.btn-ghost.btn-block", { type: "button", onclick: () => { history.replaceState(null, "", "#/add"); toast("Ready for another"); ctx.navigate("/add"); } }, "Add another")),
      hint);
    reveal(card);
    page.append(card);
  }
}
