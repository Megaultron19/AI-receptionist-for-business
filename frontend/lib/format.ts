/** Paise -> "₹1,23,456.50" (Indian digit grouping, paise only when non-zero). */
export function rupees(paise: number | null | undefined): string {
  if (paise == null) return "-";
  const sign = paise < 0 ? "-" : "";
  const abs = Math.abs(paise);
  const r = Math.floor(abs / 100);
  const p = abs % 100;
  return `${sign}₹${r.toLocaleString("en-IN")}${p ? "." + String(p).padStart(2, "0") : ""}`;
}

/** "18.50" or "18" -> 1850 paise; throws on invalid input. */
export function toPaise(rupeeText: string): number {
  const s = rupeeText.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(s)) throw new Error(`Invalid amount: ${rupeeText}`);
  const [r, p = ""] = s.split(".");
  return Number(r) * 100 + Number(p.padEnd(2, "0"));
}

export function fmtDateTime(iso: string | null | undefined, tz: string): string {
  if (!iso) return "-";
  return new Intl.DateTimeFormat("en-IN", { timeZone: tz, weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}

export function fmtTime(iso: string | null | undefined, tz: string): string {
  if (!iso) return "-";
  return new Intl.DateTimeFormat("en-IN", { timeZone: tz, hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}

/** Today's date (YYYY-MM-DD) in the restaurant's timezone. */
export function todayIn(tz: string, offsetDays = 0): string {
  const d = new Date(Date.now() + offsetDays * 86400000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export function label(s: string): string {
  return s.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const STATUS_COLORS: Record<string, string> = {
  confirmed: "bg-green-100 text-green-800", held: "bg-amber-100 text-amber-800", arrived: "bg-sky-100 text-sky-800",
  seated: "bg-indigo-100 text-indigo-800", completed: "bg-stone-200 text-stone-700", cancelled: "bg-red-100 text-red-800",
  no_show: "bg-red-100 text-red-800", draft: "bg-stone-100 text-stone-700", awaiting_payment: "bg-amber-100 text-amber-800",
  payment_pending: "bg-amber-100 text-amber-800", paid: "bg-green-100 text-green-800", submitted: "bg-orange-100 text-orange-800",
  accepted: "bg-sky-100 text-sky-800", preparing: "bg-indigo-100 text-indigo-800", ready: "bg-green-100 text-green-800",
  refunded: "bg-stone-200 text-stone-700", created: "bg-amber-100 text-amber-800", pending: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-800", expired: "bg-stone-200 text-stone-700", partially_refunded: "bg-stone-200 text-stone-700",
  open: "bg-amber-100 text-amber-800", done: "bg-green-100 text-green-800",
};

/** Hours since local midnight of `day` (YYYY-MM-DD) in `tz`; 25.5 = 01:30 the next morning. */
export function hoursInDay(iso: string, day: string, tz: string): number {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)!.value;
  const dayDiff = (Date.parse(`${get("year")}-${get("month")}-${get("day")}`) - Date.parse(day)) / 86400000;
  return dayDiff * 24 + Number(get("hour")) + Number(get("minute")) / 60;
}

/** "HH:MM" in tz, 24-hour (for <input type=time>). */
export function hhmm(iso: string, tz: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}
