"use client";
import { ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorText, Field, Notice, PageHeader, useAction } from "@/components/ui";

type S = Record<string, any>;
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const TEMPLATE_KINDS = ["booking_confirmation", "booking_reminder", "waitlist_offer", "payment_link", "order_update", "cancellation", "staff_alert"];

function hoursToText(iv: string[][]): string { return iv.map(([a, b]) => `${a}-${b}`).join(", "); }
function textToHours(t: string): string[][] { return t.split(",").map((s) => s.trim()).filter(Boolean).map((s) => s.split("-").map((x) => x.trim())); }

export default function SettingsPage() {
  const s = useApi<S>("/api/settings");
  const [form, setForm] = useState<S | null>(null);
  useEffect(() => { if (s.data) setForm(structuredClone(s.data)); }, [s.data]);
  if (!form) return <ErrorText error={s.error} />;
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });
  const text = (k: string, l: string, props: any = {}) => <Field label={l}><input className="input" value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} {...props} /></Field>;
  const num = (k: string, l: string) => <Field label={l}><input className="input" type="number" value={form[k] ?? 0} onChange={(e) => set(k, Number(e.target.value))} /></Field>;
  const bool = (k: string, l: string) => <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form[k]} onChange={(e) => set(k, e.target.checked)} />{l}</label>;

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" />
      <Section title="Restaurant profile & GST" fields={["name", "name_pronunciation", "legal_name", "address", "city", "state", "state_code", "pincode", "phone", "maps_url", "gstin", "fssai_license", "timezone", "arrival_instructions", "pickup_instructions"]} form={form} onSaved={s.reload}>
        <div className="grid gap-3 md:grid-cols-2">
          {text("name", "Restaurant name")}{text("name_pronunciation", "How the voice agent should say it")}{text("legal_name", "Legal name (invoices)")}{text("phone", "Public phone (+91…)")}
          {text("address", "Address")}{text("city", "City")}{text("state", "State")}{text("state_code", "GST state code (e.g. 29)")}{text("pincode", "PIN code")}{text("maps_url", "Google Maps link")}
          {text("gstin", "GSTIN")}{text("fssai_license", "FSSAI licence (14 digits)")}{text("timezone", "Timezone")}
          {text("arrival_instructions", "Arrival instructions (in confirmations)")}{text("pickup_instructions", "Pickup instructions")}
        </div>
      </Section>

      <Section title="Opening hours" fields={["opening_hours"]} form={form} onSaved={s.reload}>
        <p className="mb-2 text-xs text-stone-500">Format: 12:00-15:30, 19:00-23:00. Leave empty for closed. An end before the start runs past midnight (19:00-01:00).</p>
        <div className="grid gap-2 md:grid-cols-2">{DAYS.map((d) => (
          <Field key={d} label={d.toUpperCase()}><input className="input" value={hoursToText(form.opening_hours[d] ?? [])}
            onChange={(e) => set("opening_hours", { ...form.opening_hours, [d]: textToHours(e.target.value) })} /></Field>))}</div>
      </Section>
      <SpecialDays />

      <Section title="Reservation rules" fields={["reservations_enabled", "slot_interval_minutes", "default_duration_minutes", "duration_rules", "buffer_minutes", "min_notice_minutes", "max_advance_days", "min_party", "max_party", "hold_minutes", "deposit_per_guest_paise", "deposit_min_party", "cancellation_cutoff_minutes", "cancellation_policy", "no_show_grace_minutes", "reminder_offsets_minutes"]} form={form} onSaved={s.reload}>
        <div className="grid gap-3 md:grid-cols-3">
          {bool("reservations_enabled", "Taking reservations")}
          <Field label="Slot interval (min)"><select className="input" value={form.slot_interval_minutes} onChange={(e) => set("slot_interval_minutes", Number(e.target.value))}>{[5, 10, 15, 20, 30, 60].map((m) => <option key={m}>{m}</option>)}</select></Field>
          {num("default_duration_minutes", "Sitting length (min)")}{num("buffer_minutes", "Cleaning buffer (min)")}{num("min_notice_minutes", "Minimum notice (min)")}{num("max_advance_days", "Book up to (days ahead)")}
          {num("min_party", "Min party")}{num("max_party", "Max party (online)")}{num("hold_minutes", "Hold for deposit/offer (min)")}
          <Field label="Deposit per guest (₹)"><input className="input" value={form.deposit_per_guest_paise / 100} onChange={(e) => set("deposit_per_guest_paise", Math.round((Number(e.target.value) || 0) * 100))} /></Field>
          {num("deposit_min_party", "Deposit from party size (0 = off)")}{num("cancellation_cutoff_minutes", "Customer cancel cutoff (min)")}{num("no_show_grace_minutes", "No-show after (min late)")}
          <Field label="Longer sittings (party:minutes, …)"><input className="input" value={(form.duration_rules ?? []).map((r: any) => `${r.min_party}:${r.minutes}`).join(", ")}
            onChange={(e) => set("duration_rules", e.target.value.split(",").map((x) => x.trim()).filter(Boolean).map((x) => { const [p, m] = x.split(":"); return { min_party: Number(p), minutes: Number(m) }; }))} /></Field>
          <Field label="Reminders (minutes before, comma-separated)"><input className="input" value={(form.reminder_offsets_minutes ?? []).join(", ")}
            onChange={(e) => set("reminder_offsets_minutes", e.target.value.split(",").map((x) => Number(x.trim())).filter(Boolean))} /></Field>
        </div>
        <Field label="Cancellation policy (told to customers)" className="mt-3"><textarea className="input" rows={2} value={form.cancellation_policy} onChange={(e) => set("cancellation_policy", e.target.value)} /></Field>
      </Section>

      <Section title="Ordering, taxes & charges" fields={["ordering_enabled", "prep_target_minutes", "kitchen_parallel_orders", "max_active_orders", "auto_accept_orders", "min_payment_type", "min_payment_value", "default_tax_rate_bp", "prices_include_tax", "charges", "discounts", "invoice_prefix"]} form={form} onSaved={s.reload}>
        <div className="grid gap-3 md:grid-cols-3">
          {bool("ordering_enabled", "Taking pre-orders")}{bool("auto_accept_orders", "Auto-accept when kitchen has capacity")}{bool("prices_include_tax", "Menu prices include GST")}
          {num("prep_target_minutes", "Preparation target (min)")}{num("kitchen_parallel_orders", "Orders cooked in parallel")}{num("max_active_orders", "Max open orders")}
          <Field label="Default GST %"><input className="input" value={form.default_tax_rate_bp / 100} onChange={(e) => set("default_tax_rate_bp", Math.round(Number(e.target.value) * 100))} /></Field>
          <Field label="Pay online before kitchen"><select className="input" value={form.min_payment_type} onChange={(e) => set("min_payment_type", e.target.value)}>
            <option value="full">Full amount</option><option value="percent">Percentage</option><option value="flat">Fixed advance</option><option value="none">Nothing (pay at restaurant)</option></select></Field>
          {form.min_payment_type === "percent" && <Field label="Advance %"><input className="input" value={form.min_payment_value / 100} onChange={(e) => set("min_payment_value", Math.round(Number(e.target.value) * 100))} /></Field>}
          {form.min_payment_type === "flat" && <Field label="Advance ₹"><input className="input" value={form.min_payment_value / 100} onChange={(e) => set("min_payment_value", Math.round((Number(e.target.value) || 0) * 100))} /></Field>}
          {text("invoice_prefix", "Invoice prefix")}
        </div>
        <JsonList label="Charges" hint='e.g. [{"name":"Packaging","kind":"flat","value":2000,"taxable":true,"applies_to":"pickup"}] - value in paise (flat) or basis points (percent: 500 = 5%)'
          value={form.charges} onChange={(v) => set("charges", v)} />
        <JsonList label="Discounts" hint='e.g. [{"name":"10% off above ₹1,500","percent_bp":1000,"min_subtotal_paise":150000,"active":true}]' value={form.discounts} onChange={(v) => set("discounts", v)} />
      </Section>

      <Section title="AI receptionist" fields={["ai_enabled", "languages", "primary_language", "greeting_en", "greeting_hi", "ai_knowledge", "transfer_number", "staff_alert_numbers"]} form={form} onSaved={s.reload}>
        <div className="grid gap-3 md:grid-cols-2">
          {bool("ai_enabled", "AI answers calls and WhatsApp (off = everything goes to staff)")}
          <Field label="Primary language"><select className="input" value={form.primary_language} onChange={(e) => set("primary_language", e.target.value)}><option value="en-IN">English (India)</option><option value="hi-IN">Hindi</option></select></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.languages.includes("hi-IN")} onChange={(e) => set("languages", e.target.checked ? ["en-IN", "hi-IN"] : ["en-IN"])} /> Offer Hindi (press 2 on calls)</label>
          {text("transfer_number", "Transfer calls to (+91…)")}
          <Field label="Staff WhatsApp alert numbers (comma-separated)"><input className="input" value={(form.staff_alert_numbers ?? []).join(", ")} onChange={(e) => set("staff_alert_numbers", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field>
          <Field label="Greeting (English) - blank for default"><textarea className="input" rows={2} value={form.greeting_en} onChange={(e) => set("greeting_en", e.target.value)} /></Field>
          <Field label="Greeting (Hindi)"><textarea className="input" rows={2} value={form.greeting_hi} onChange={(e) => set("greeting_hi", e.target.value)} /></Field>
        </div>
        <Field label="Approved information the AI may share (parking, policies, FAQs…)" className="mt-3"><textarea className="input" rows={6} value={form.ai_knowledge} onChange={(e) => set("ai_knowledge", e.target.value)} /></Field>
      </Section>

      <Section title="WhatsApp templates & data retention" fields={["whatsapp_templates", "transcript_retention_days"]} form={form} onSaved={s.reload}>
        <p className="mb-2 text-xs text-stone-500">Names of templates approved in Meta Business Manager, used outside the 24-hour window for customers who consented. See docs/whatsapp.md for the variables each template must have.</p>
        <div className="grid gap-2 md:grid-cols-2">{TEMPLATE_KINDS.map((k) => (
          <Field key={k} label={k.replaceAll("_", " ")}><input className="input" placeholder="template_name" value={form.whatsapp_templates?.[k]?.name ?? ""}
            onChange={(e) => { const t = { ...(form.whatsapp_templates ?? {}) }; if (e.target.value) t[k] = { name: e.target.value, language: t[k]?.language ?? "en" }; else delete t[k]; set("whatsapp_templates", t); }} /></Field>))}</div>
        <div className="mt-3 w-60">{num("transcript_retention_days", "Delete chat transcripts after (days)")}</div>
      </Section>
    </div>
  );
}

function Section({ title, fields, form, onSaved, children }: { title: string; fields: string[]; form: S; onSaved: () => void; children: ReactNode }) {
  const act = useAction();
  const [ok, setOk] = useState("");
  return (
    <section className="card">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
      <div className="mt-3 flex items-center gap-3">
        <button className="btn" disabled={act.busy} onClick={async () => {
          setOk("");
          const body = Object.fromEntries(fields.map((f) => [f, form[f]]));
          if (await act.run(() => api("/api/settings", { method: "PATCH", body }))) { setOk("Saved."); onSaved(); }
        }}>Save</button>
        <Notice text={ok} /><ErrorText error={act.error} />
      </div>
    </section>
  );
}

function JsonList({ label, hint, value, onChange }: { label: string; hint: string; value: any[]; onChange: (v: any[]) => void }) {
  const [text, setText] = useState(JSON.stringify(value ?? [], null, 0));
  const [err, setErr] = useState("");
  return (
    <Field label={label} className="mt-3">
      <textarea className="input font-mono text-xs" rows={2} value={text} onChange={(e) => {
        setText(e.target.value);
        try { onChange(JSON.parse(e.target.value || "[]")); setErr(""); } catch { setErr("Not valid JSON yet"); }
      }} />
      <span className="text-xs text-stone-500">{err || hint}</span>
    </Field>
  );
}

function SpecialDays() {
  const days = useApi<{ id: number; day: string; closed: boolean; intervals: string[][]; note: string }[]>("/api/special-days");
  const [f, setF] = useState({ day: "", closed: true, intervals: "", note: "" });
  const act = useAction();
  return (
    <section className="card">
      <h2 className="mb-3 font-semibold">Holidays & special hours</h2>
      <table className="table"><tbody>{days.data?.map((d) => (
        <tr key={d.id}><td>{d.day}</td><td>{d.closed ? "Closed" : hoursToText(d.intervals)}</td><td>{d.note}</td>
          <td className="text-right"><button className="btn-ghost" onClick={async () => { await act.run(() => api(`/api/special-days/${d.id}`, { method: "DELETE" })); days.reload(); }}>Remove</button></td></tr>))}</tbody></table>
      <div className="mt-3 grid gap-2 md:grid-cols-4">
        <input className="input" type="date" value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} aria-label="Date" />
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.closed} onChange={(e) => setF({ ...f, closed: e.target.checked })} /> Closed all day</label>
        {!f.closed && <input className="input" placeholder="12:00-16:00" value={f.intervals} onChange={(e) => setF({ ...f, intervals: e.target.value })} />}
        <input className="input" placeholder="Note (e.g. Diwali)" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
      </div>
      <p className="mt-1 text-xs text-stone-500">Existing bookings on that day are not cancelled automatically - check the reservations list.</p>
      <div className="mt-2 flex gap-2"><button className="btn" disabled={!f.day || act.busy} onClick={async () => {
        if (await act.run(() => api("/api/special-days", { method: "PUT", body: { day: f.day, closed: f.closed, intervals: f.closed ? [] : textToHours(f.intervals), note: f.note } }))) { setF({ day: "", closed: true, intervals: "", note: "" }); days.reload(); }
      }}>Add</button><ErrorText error={act.error} /></div>
    </section>
  );
}
