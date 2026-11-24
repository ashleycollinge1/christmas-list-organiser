import { api } from "../api.js";
import { h, icon, reveal, toast, busy, formError, copyText } from "../dom.js";
import { field } from "../sheet.js";

export function render(main, ctx) {
  const user = ctx.session.user;
  const nameErr = h("div", { "aria-live": "assertive" });
  const nameSave = h("button.btn", { type: "submit", dataset: { busyLabel: "Saving…" } }, "Save name");
  const nameForm = h("form.form.card", { novalidate: true },
    h("h2.card-title", "Your name"),
    nameErr,
    field("Display name", { name: "display_name", value: user.display_name || "", autocomplete: "name", autocapitalize: "words", placeholder: user.username }, {
      hint: "Shown to people you share recipients with.",
    }),
    nameSave);
  nameForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    nameErr.replaceChildren();
    await busy(nameSave, async () => {
      try {
        const res = await api("/api/auth/me", { method: "PATCH", body: { display_name: nameForm.display_name.value } });
        ctx.setSession(res.user);
        toast("Name saved");
      } catch (ex) {
        nameErr.append(formError(ex.message));
      }
    });
  });

  const pwErr = h("div", { "aria-live": "assertive" });
  const pwSave = h("button.btn", { type: "submit", dataset: { busyLabel: "Saving…" } }, "Change password");
  const pwForm = h("form.form.card", { novalidate: true },
    h("h2.card-title", "Password"),
    pwErr,
    h("input", { type: "text", name: "username", autocomplete: "username", value: user.username, hidden: true, readonly: true }),
    field("Current password", { type: "password", name: "current", autocomplete: "current-password", required: true }),
    field("New password", { type: "password", name: "next", autocomplete: "new-password", required: true }, { hint: "At least 12 characters. Other devices will be signed out." }),
    field("Confirm new password", { type: "password", name: "confirm", autocomplete: "new-password", required: true }),
    pwSave);
  pwForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    pwErr.replaceChildren();
    if (pwForm.next.value !== pwForm.confirm.value) {
      pwErr.append(formError("The new passwords don't match."));
      return;
    }
    await busy(pwSave, async () => {
      try {
        await api("/api/auth/password", { method: "POST", body: { current_password: pwForm.current.value, new_password: pwForm.next.value } });
        pwForm.reset();
        toast("Password changed");
      } catch (ex) {
        pwErr.append(formError(ex.message));
      }
    });
  });

  // The iOS Shortcut: Safari's Share button -> this server's /share?url=… -> the add-a-wish form.
  const shareBase = `${location.origin}/share?url=`;
  const shortcut = h("section.card.shortcut-card",
    h("h2.card-title", "iPhone Shortcut"),
    h("p.muted", "Add things to your wish list straight from Safari's Share button. The name and price are filled in from the page. Set it up once in the Shortcuts app:"),
    h("ol.steps",
      h("li", "Open the ", h("strong", "Shortcuts"), " app and tap ", h("strong", "+"), ". Rename it ", h("em", "Add to wish list"), " (tap the name at the top)."),
      h("li", "Tap ", h("strong", "ⓘ"), " at the bottom and turn on ", h("strong", "Show in Share Sheet"), ". Close that. At the top it now says ", h("em", "Receive … from Share Sheet"), ": tap the types and leave only ", h("strong", "URLs"), " and ", h("strong", "Safari web pages"), "."),
      h("li", "Add the action ", h("strong", "URL Encode"), ". It encodes the ", h("em", "Shortcut Input"), "."),
      h("li", "Add the action ", h("strong", "URL"), ". Paste the address below into it, then tap at the very end and choose the ", h("em", "URL Encoded Text"), " variable from the bar above the keyboard."),
      h("li", "Add the action ", h("strong", "Show Web Page"), ". It shows the ", h("em", "URL"), " from the step before. Tap ", h("strong", "Done"), "."),
    ),
    h("p.secret.mono", shareBase),
    h("button.btn.btn-block", { type: "button", onclick: () => copyText(shareBase, "Address copied") }, icon("copy"), "Copy address"),
    h("p.muted.small", "To use it, in Safari: Share → Add to wish list (scroll the actions, or use Edit Actions to make it a favourite). The first time, sign in inside the window that opens; it stays signed in for 30 days. Use “Open URLs” instead of “Show Web Page” if you'd rather it opened in Safari itself."));

  const head = h("header.page-head",
    h("p.eyebrow", `@${user.username}`),
    h("h1.page-title", "Account"));
  const out = h("button.btn.btn-ghost.btn-block", { type: "button", onclick: ctx.signOut }, icon("logout"), "Sign out");
  const ver = h("p.muted.small.center", `Version ${ctx.session.version || "dev"}`);
  reveal(head, nameForm, pwForm, shortcut, out);
  main.append(h("div.page.account", head, nameForm, pwForm, shortcut, out, ver));
}
