// Money, status and date formatting. Money is integer pence everywhere.

const whole = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const exact = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", minimumFractionDigits: 2 });

export function money(pence) {
  if (pence == null) return "—";
  return pence % 100 === 0 ? whole.format(pence / 100) : exact.format(pence / 100);
}

/** "£1,234.50" / "1234.5" / "12" → pence. Empty → null. Invalid → NaN. */
export function parseMoney(text) {
  const raw = String(text ?? "").trim().replace(/[£,\s]/g, "");
  if (!raw) return null;
  if (!/^\d+(\.\d{0,2})?$/.test(raw)) return NaN;
  const [pounds, frac = ""] = raw.split(".");
  return Number(pounds) * 100 + Number((frac + "00").slice(0, 2));
}

/** Pence → value for an input ("12.50", or "300" when whole). */
export function moneyInput(pence) {
  if (pence == null) return "";
  return pence % 100 === 0 ? String(pence / 100) : (pence / 100).toFixed(2);
}

export const STATUSES = [
  { value: "idea", label: "Idea" },
  { value: "ordered", label: "Ordered" },
  { value: "reorder", label: "Reorder" },
  { value: "delivered", label: "Delivered" },
  { value: "wrapped", label: "Wrapped" },
  { value: "given", label: "Given" },
];
export const STATUS_LABEL = Object.fromEntries(STATUSES.map((s) => [s.value, s.label]));

// The usual path; "reorder" is a detour that goes back to "ordered".
const FLOW = ["idea", "ordered", "delivered", "wrapped", "given"];

export function nextStatus(status) {
  if (status === "reorder") return "ordered";
  const i = FLOW.indexOf(status);
  return i >= 0 && i < FLOW.length - 1 ? FLOW[i + 1] : null;
}

export const PRIORITIES = [
  { value: 1, label: "High" },
  { value: 2, label: "Medium" },
  { value: 3, label: "Low" },
];
export const PRIORITY_LABEL = { 1: "High", 2: "Medium", 3: "Low" };

const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" });
const fullFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

function localDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** "Today", "Tomorrow", "Thu 10 Dec", plus whether it's in the past. */
export function deliveryDay(iso) {
  if (!iso) return null;
  const d = localDate(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((d - today) / 86400000);
  let text = dayFmt.format(d);
  if (days === 0) text = "Today";
  else if (days === 1) text = "Tomorrow";
  else if (days === -1) text = "Yesterday";
  return { text, overdue: days < 0 };
}

export function dateLong(iso) {
  return iso ? fullFmt.format(new Date(iso)) : "";
}

/** Budget state → short human phrase. */
export function budgetPhrase(t) {
  if (t.budget_pence == null) return t.spent_pence ? `${money(t.spent_pence)} spent` : "No budget set";
  if (t.state === "over") return `${money(-t.remaining_pence)} over`;
  if (t.state === "on") return "On budget";
  return `${money(t.remaining_pence)} left`;
}

export const KINDS = [
  { value: "christmas", label: "Christmas" },
  { value: "birthday", label: "Birthday" },
  { value: "other", label: "Other" },
];
export const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label]));

/** Occasion date: "Sat 14 Mar 2027 · in 112 days". */
export function occasionWhen(iso) {
  if (!iso) return null;
  const d = localDate(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((d - today) / 86400000);
  const when = days === 0 ? "today" : days === 1 ? "tomorrow" : days > 1 ? `in ${days} days` : days === -1 ? "yesterday" : `${-days} days ago`;
  return { date: fullFmt.format(d), when, past: days < 0, days };
}
