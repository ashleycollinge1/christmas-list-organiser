import { api, configure, setCsrf, ApiError } from "./api.js";
import { h, clear, icon, toast } from "./dom.js";
import * as loginView from "./views/login.js";
import * as homeView from "./views/home.js";
import * as occasionView from "./views/occasion.js";
import * as peopleView from "./views/people.js";
import * as meView from "./views/me.js";
import * as addView from "./views/add.js";
import * as recipientView from "./views/recipient.js";
import * as wrapView from "./views/wrap.js";
import * as adminView from "./views/admin.js";
import * as accountView from "./views/account.js";

const main = document.getElementById("main");
const topbar = document.getElementById("topbar");
const tabbar = document.getElementById("tabbar");
const navLinks = document.getElementById("nav-links");

const session = { user: null, version: "" };
let cleanup = null;
// Scroll positions per route, so "back" from a recipient lands where you were.
const scrollMemory = new Map();
let currentKey = null;

const routes = [
  { pattern: /^\/login$/, view: loginView, public: true },
  { pattern: /^\/invite\/([A-Za-z0-9_-]{10,})$/, view: loginView, public: true, mode: "invite" },
  { pattern: /^\/password$/, view: loginView, public: true, mode: "password" },
  { pattern: /^\/$/, view: homeView, nav: "home" },
  { pattern: /^\/o\/(\d+)$/, view: occasionView, nav: "home" },
  { pattern: /^\/r\/(\d+)$/, view: recipientView, nav: "home" },
  { pattern: /^\/people$/, view: peopleView, nav: "people" },
  { pattern: /^\/me$/, view: meView, nav: "people" },
  // The iOS Shortcut's form: no tab bar, so it fits the share overlay.
  { pattern: /^\/add$/, view: addView },
  { pattern: /^\/wrap$/, view: wrapView, nav: "wrap" },
  { pattern: /^\/admin$/, view: adminView, nav: "admin", admin: true },
  { pattern: /^\/account$/, view: accountView, nav: "account" },
];

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, qs = ""] = raw.split("?");
  return { path: path || "/", query: new URLSearchParams(qs), key: raw };
}

export function navigate(path, { replace = false } = {}) {
  const target = `#${path}`;
  if (location.hash === target) route();
  else if (replace) {
    history.replaceState(null, "", target);
    route();
  } else location.hash = target;
}

function renderNav(active) {
  clear(navLinks);
  const signedIn = Boolean(session.user) && !session.user.must_change_password;
  topbar.hidden = !signedIn;
  tabbar.hidden = !signedIn || !active;
  document.body.classList.toggle("has-tabbar", signedIn && Boolean(active));
  if (!signedIn) return;
  const items = [
    { id: "home", href: "#/", label: "Home", icon: "home" },
    { id: "people", href: "#/people", label: "People", icon: "users" },
    { id: "wrap", href: "#/wrap", label: "Wrapping", icon: "ribbon" },
    session.user.role === "admin" && { id: "admin", href: "#/admin", label: "Admin", icon: "shield" },
    { id: "account", href: "#/account", label: "Account", icon: "user" },
  ].filter(Boolean);
  for (const it of items) {
    navLinks.append(h("li", h("a.tab", { href: it.href, "aria-current": it.id === active ? "page" : null },
      icon(it.icon), h("span", it.label))));
  }
}

const TITLES = { christmas: "Christmas", birthday: "Birthday", other: "Gift" };

/** Header and tab title follow the occasion being viewed: Christmas List, Birthday List or Gift List. */
export function setOccasion(occasion) {
  const tag = document.getElementById("season-tag");
  tag.textContent = occasion ? occasion.name : "";
  tag.classList.toggle("is-archived", Boolean(occasion?.is_archived));
  const word = TITLES[occasion?.kind] || "Gift";
  const brand = document.querySelector(".brand-word");
  brand.replaceChildren(`${word} `, h("em", "List"));
  document.querySelector(".brand").setAttribute("aria-label", `${word} List: home`);
  document.title = occasion ? `${occasion.name} · ${word} List` : "Gift List";
}

async function signOut() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch { /* already signed out */ }
  session.user = null;
  setCsrf(null);
  navigate("/login");
}

async function loadSession() {
  try {
    const me = await api("/api/auth/me");
    session.user = me.user;
    session.version = me.version;
    setCsrf(me.csrf_token);
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 401) throw err;
    session.user = null;
  }
}

function setSession(user, csrf) {
  session.user = user;
  if (csrf) setCsrf(csrf);
}

/** Where to go once signed in: the page that asked for login, or Home. */
function afterLogin() {
  const next = sessionStorage.getItem("afterLogin");
  sessionStorage.removeItem("afterLogin");
  return next && next.startsWith("/") ? next : "/";
}

async function route() {
  const { path, query, key } = parseHash();
  let match = null;
  let params = [];
  for (const r of routes) {
    const m = path.match(r.pattern);
    if (m) { match = r; params = m.slice(1); break; }
  }
  // v0.1.0 links: #/?season=ID
  if (path === "/" && query.get("season")) return navigate(`/o/${query.get("season")}`, { replace: true });
  if (!match) return navigate("/", { replace: true });

  const user = session.user;
  if (!match.public && !user) {
    // Come back here after signing in (e.g. the share form opened by the iOS Shortcut).
    if (path !== "/") sessionStorage.setItem("afterLogin", key);
    return navigate("/login", { replace: true });
  }
  if (user?.must_change_password && match.mode !== "password") return navigate("/password", { replace: true });
  if (match.public && user && !match.mode) return navigate("/", { replace: true });
  if (match.mode === "invite" && user) return navigate("/", { replace: true });
  if (match.mode === "password" && !user) return navigate("/login", { replace: true });
  if (match.admin && user.role !== "admin") return navigate("/", { replace: true });

  if (currentKey) scrollMemory.set(currentKey, window.scrollY);
  currentKey = key;

  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  renderNav(match.nav);
  setOccasion(null);
  clear(main);
  window.scrollTo(0, 0);
  try {
    cleanup = (await match.view.render(main, {
      session, params, query, mode: match.mode, navigate, setSession, signOut, setOccasion, afterLogin,
    })) || null;
    const y = scrollMemory.get(key);
    if (y) window.scrollTo(0, y);
  } catch (err) {
    console.error(err);
    if (err instanceof ApiError && err.status === 401) return;
    clear(main).append(
      h("section.page", h("div.error-state", { role: "alert" },
        h("h2", err.status === 404 ? "Not found" : "Something went wrong"),
        h("p", err.message || String(err)),
        h("div.row",
          h("button.btn", { type: "button", onclick: () => route() }, icon("retry"), "Try again"),
          h("a.btn.btn-ghost", { href: "#/" }, "Home")))),
    );
  }
  // Move focus for screen readers on route change (not on first load).
  if (route.ran) main.focus({ preventScroll: true });
  route.ran = true;
}

configure({
  onAuthLost: () => {
    if (!session.user) return;
    session.user = null;
    toast("Your session ended. Please sign in again.", "error");
    navigate("/login");
  },
  onPasswordRequired: () => {
    if (session.user) session.user.must_change_password = true;
    navigate("/password");
  },
});

window.addEventListener("hashchange", route);
// Tell the user when the connection drops instead of failing silently.
window.addEventListener("offline", () => toast("You're offline. Changes won't save until you reconnect.", "error"));

(async function boot() {
  try {
    await loadSession();
  } catch (err) {
    clear(main).append(h("section.page", h("div.error-state", { role: "alert" },
      h("h2", "Can't reach the server"),
      h("p", err.message),
      h("button.btn", { type: "button", onclick: () => location.reload() }, icon("retry"), "Reload"))));
    return;
  }
  route();
})();
