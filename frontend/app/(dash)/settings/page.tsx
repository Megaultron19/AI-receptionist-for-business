"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, Field, Header, useAction } from "@/components/ui";
import { useMe } from "@/components/Shell";

const DAYS: [string, string][] = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
type Settings = { name: string; phone: string; address: string; about: string; hours: Record<string, string[][]>; slot_minutes: number; dining_minutes: number; max_guests: number; advance_days: number; prep_target_minutes: number; staff_phone: string };

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
        <Field label="Staff phone (calls are transferred here)"><input className="input" value={f.staff_phone} onChange={(e) => set("staff_phone", e.target.value)} /></Field>
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
        {num("advance_days", "Book up to (days ahead, max 7)")}
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
      <Logins />
    </div>
  );
}

type Login = { id: number; username: string; role: string; active: boolean };

function Logins() {
  const me = useMe();
  const users = useApi<Login[]>("/api/users");
  const [f, setF] = useState({ username: "", password: "", role: "staff" });
  const act = useAction();

  async function run(fn: () => Promise<unknown>) {
    if (await act.run(fn)) users.reload();
  }

  return (
    <section className="card">
      <h2 className="mb-3 font-semibold">Logins</h2>
      <table className="table-list mb-4">
        <thead><tr><th>Username</th><th>Role</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {users.data?.map((u) => (
            <tr key={u.id} className={u.active ? "" : "text-stone-400"}>
              <td>{u.username}</td><td>{u.role === "owner" ? "Owner" : "Staff"}</td><td>{u.active ? "Active" : "Turned off"}</td>
              <td className="flex justify-end gap-1">{u.username !== me.username && <>
                <button className="btn-light" onClick={() => {
                  const password = window.prompt(`New password for ${u.username} (at least 8 characters)`);
                  if (password) run(() => api(`/api/users/${u.id}/password`, "POST", { password }));
                }}>Change password</button>
                <button className="btn-light" onClick={() => run(() => api(`/api/users/${u.id}/active?active=${!u.active}`, "POST"))}>
                  {u.active ? "Turn off" : "Turn on"}
                </button>
              </>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="grid gap-2 md:grid-cols-4" onSubmit={async (e) => {
        e.preventDefault();
        if (await act.run(() => api("/api/users", "POST", f))) { setF({ username: "", password: "", role: "staff" }); users.reload(); }
      }}>
        <Field label="Username"><input className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
        <Field label="Password"><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <Field label="Role">
          <select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            <option value="staff">Staff (door, bookings, orders)</option>
            <option value="owner">Owner (everything)</option>
          </select>
        </Field>
        <div className="flex items-end"><button className="btn w-full" disabled={act.busy || !f.username || f.password.length < 8}>Add login</button></div>
      </form>
      <div className="mt-2"><ErrorBox text={users.error || act.error} /></div>
    </section>
  );
}
