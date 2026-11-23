import { api } from "../api.js";
import { h, reveal, formError, busy, autofocus, icon } from "../dom.js";

function hero(lede) {
  const eyebrow = h("p.eyebrow", "Christmas List");
  const title = h("h1.auth-title", h("span.thin", "Every gift,"), h("br"), h("em", "sorted."));
  const p = h("p.lede", lede);
  reveal(eyebrow, title, p);
  return h("section.auth-hero", h("span.auth-star", { "aria-hidden": "true" }), eyebrow, title, p);
}

function textField(id, label, attrs = {}, hint) {
  return h("div.field",
    h("label", { for: id }, label),
    h(`input.input#${id}`, { name: id, "aria-describedby": hint ? `${id}-hint` : null, ...attrs }),
    hint && h(`p.hint#${id}-hint`, hint));
}

function passwordField(id, label, autocomplete, hint) {
  return textField(id, label, { type: "password", required: true, autocomplete }, hint);
}

function usernameAttrs(autocomplete) {
  return { autocomplete, required: true, autocapitalize: "none", autocorrect: "off", spellcheck: "false", enterkeyhint: "next" };
}

export function render(main, ctx) {
  const wrap = h("div.auth");
  const formSide = h("section.auth-form-wrap");
  main.append(wrap);
  if (ctx.mode === "password") {
    wrap.append(hero("Choose a password only you know before you carry on."), formSide);
    return renderPassword(formSide, ctx);
  }
  if (ctx.mode === "invite") {
    wrap.append(hero("You've been invited. Set up your account to start planning gifts."), formSide);
    return renderInvite(formSide, ctx);
  }
  wrap.append(hero("Budgets, links and a traffic light for every present, from idea to wrapped."), formSide);
  return renderLogin(formSide, ctx);
}

function renderLogin(host, ctx) {
  const err = h("div", { "aria-live": "assertive" });
  const submit = h("button.btn.btn-primary.btn-block", { type: "submit", dataset: { busyLabel: "Signing in…" } }, "Sign in");
  const form = h("form.form.card", { novalidate: true },
    h("h2", "Sign in"),
    err,
    textField("username", "Username", usernameAttrs("username")),
    passwordField("password", "Password", "current-password"),
    submit);
  reveal(form);
  host.append(form);
  autofocus(form.username);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.replaceChildren();
    const username = form.username.value.trim();
    const password = form.password.value;
    form.username.setAttribute("aria-invalid", String(!username));
    form.password.setAttribute("aria-invalid", String(!password));
    if (!username || !password) {
      err.append(formError("Enter your username and password."));
      return;
    }
    await busy(submit, async () => {
      try {
        const res = await api("/api/auth/login", { method: "POST", body: { username, password } });
        ctx.setSession(res.user, res.csrf_token);
        ctx.navigate(res.user.must_change_password ? "/password" : "/");
      } catch (ex) {
        err.append(formError(ex.message));
        form.password.value = "";
      }
    });
  });
}

function renderPassword(host, ctx) {
  const err = h("div", { "aria-live": "assertive" });
  const submit = h("button.btn.btn-primary.btn-block", { type: "submit", dataset: { busyLabel: "Saving…" } }, "Set password & continue");
  const form = h("form.form.card", { novalidate: true },
    h("h2", "Set your password"),
    h("p.muted", "You signed in with a temporary password."),
    err,
    // Hidden username so iOS Keychain saves the new password against the right account.
    h("input", { type: "text", name: "username", autocomplete: "username", value: ctx.session.user?.username || "", hidden: true, readonly: true }),
    passwordField("current", "Temporary password", "current-password"),
    passwordField("next", "New password", "new-password", "At least 12 characters."),
    passwordField("confirm", "Confirm new password", "new-password"),
    submit,
    h("button.btn.btn-ghost.btn-block", { type: "button", onclick: ctx.signOut }, icon("logout"), "Sign out"));
  reveal(form);
  host.append(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.replaceChildren();
    if (form.next.value !== form.confirm.value) {
      err.append(formError("The new passwords don't match."));
      return;
    }
    await busy(submit, async () => {
      try {
        const res = await api("/api/auth/password", {
          method: "POST",
          body: { current_password: form.current.value, new_password: form.next.value },
        });
        ctx.setSession(res.user);
        ctx.navigate("/");
      } catch (ex) {
        err.append(formError(ex.message));
      }
    });
  });
}

async function renderInvite(host, ctx) {
  const token = ctx.params[0];
  try {
    await api(`/api/auth/invite/${token}`);
  } catch (ex) {
    const card = h("div.card.error-state", { role: "alert" },
      h("h2", "This invite can't be used"),
      h("p", ex.message),
      h("p.muted", "Ask whoever sent it for a new link."),
      h("a.btn", { href: "#/login" }, "Go to sign in"));
    reveal(card);
    host.append(card);
    return;
  }
  const err = h("div", { "aria-live": "assertive" });
  const submit = h("button.btn.btn-primary.btn-block", { type: "submit", dataset: { busyLabel: "Creating…" } }, "Create account");
  const form = h("form.form.card", { novalidate: true },
    h("h2", "Create your account"),
    err,
    textField("display_name", "Your name", { autocomplete: "name", enterkeyhint: "next", placeholder: "e.g. Sam" },
      "Shown to people you share recipients with."),
    textField("username", "Username", usernameAttrs("username"), "Letters, numbers, dots or dashes."),
    passwordField("password", "Password", "new-password", "At least 12 characters."),
    passwordField("confirm", "Confirm password", "new-password"),
    submit);
  reveal(form);
  host.append(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.replaceChildren();
    if (form.password.value !== form.confirm.value) {
      err.append(formError("The passwords don't match."));
      return;
    }
    await busy(submit, async () => {
      try {
        const res = await api(`/api/auth/invite/${token}`, {
          method: "POST",
          body: {
            username: form.username.value.trim(),
            display_name: form.display_name.value.trim() || null,
            password: form.password.value,
          },
        });
        ctx.setSession(res.user, res.csrf_token);
        history.replaceState(null, "", "#/");
        ctx.navigate("/", { replace: true });
      } catch (ex) {
        err.append(formError(ex.message));
      }
    });
  });
}
