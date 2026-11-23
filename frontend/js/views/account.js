import { api } from "../api.js";
import { h, icon, reveal, toast, busy, formError } from "../dom.js";
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

  const head = h("header.page-head",
    h("p.eyebrow", `@${user.username}`),
    h("h1.page-title", "Account"));
  const out = h("button.btn.btn-ghost.btn-block", { type: "button", onclick: ctx.signOut }, icon("logout"), "Sign out");
  const ver = h("p.muted.small.center", `Version ${ctx.session.version || "dev"}`);
  reveal(head, nameForm, pwForm, out);
  main.append(h("div.page.account", head, nameForm, pwForm, out, ver));
}
