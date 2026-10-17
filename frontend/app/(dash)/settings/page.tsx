"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, Field, Header, useAction } from "@/components/ui";

const DAYS: [string, string][] = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
type Settings = { name: string; phone: string; address: string; about: string; hours: Record<string, string[][]>; slot_minutes: number; dining_minutes: number; max_guests: number; advance_days: number; prep_target_minutes: number };

const toText = (windows: string[][]) => windows.map((w) => w.join("-")).join(", ");
const toWindows = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean).map((s) => s.split("-").map((t) => t.trim()));

export default function SettingsPage() {
  const saved = useApi<Settings>("/api/restaurant");
  const [f, setF] = useState<Settings | null>(null);
  const [hours, setHours] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const act = useAction();

  useEffect(() => {
    if (!saved.data) return;
    setF(saved.data);
    setHours(Object.fromEntries(DAYS.map(([d]) => [d, toText(saved.data!.hours[d] ?? [])])));
  }, [saved.data]);

  if (!f) return <ErrorBox text={saved.error} />;
  const set = (k: keyof Settings, v: unknown) => setF({ ...f, [k]: v });
  const num = (k: keyof Settings, label: string) => (
    <Field label={label}><input className="input" type="number" value={f[k] as number} onChange={(e) => set(k, Number(e.target.value))} /></Field>
  );

  return (
    <div className="space-y-4">
      <Header title="Settings" />
      <section className="card grid gap-3 md:grid-cols-2">
        <Field label="Restaurant name"><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="Address"><input className="input" value={f.address} onChange={(e) => set("address", e.target.value)} /></Field>
        <Field label="About (parking, timings, policies the receptionist can share)"><textarea className="input" rows={3} value={f.about} onChange={(e) => set("about", e.target.value)} /></Field>
      </section>
      <section className="card">
        <h2 className="mb-1 font-semibold">Opening hours</h2>
        <p className="mb-3 text-xs text-stone-500">Example: 12:00-15:30, 19:00-23:00. Leave empty if closed. 19:00-01:00 means open past midnight.</p>
        <div className="grid gap-2 md:grid-cols-2">
          {DAYS.map(([d, label]) => <Field key={d} label={label}><input className="input" value={hours[d] ?? ""} onChange={(e) => setHours({ ...hours, [d]: e.target.value })} /></Field>)}
        </div>
      </section>
      <section className="card grid gap-3 md:grid-cols-3">
        {num("dining_minutes", "Table time per booking (minutes)")}
        {num("slot_minutes", "Booking slot every (minutes)")}
        {num("max_guests", "Largest party online")}
        {num("advance_days", "Book up to (days ahead)")}
        {num("prep_target_minutes", "Food ready target (minutes)")}
      </section>
      <div className="flex items-center gap-3">
        <button className="btn" disabled={act.busy} onClick={async () => {
          setDone(false);
          const body = { ...f, hours: Object.fromEntries(DAYS.map(([d]) => [d, toWindows(hours[d] ?? "")])) };
          if (await act.run(() => api("/api/restaurant", "PUT", body))) setDone(true);
        }}>Save</button>
        {done && <span className="text-sm text-green-700">Saved</span>}
        <ErrorBox text={act.error} />
      </div>
    </div>
  );
}
