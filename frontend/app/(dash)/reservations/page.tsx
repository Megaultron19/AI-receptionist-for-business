"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { fmtTime, hhmm, rupees, todayIn } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { Badge, Empty, ErrorText, Field, Modal, PageHeader, useAction } from "@/components/ui";

type Res = { ref: string; status: string; party_size: number; starts_at: string; ends_at: string; source: string; notes: string;
  staff_notes: string; hold_reason: string | null; hold_expires_at: string | null; deposit_paise: number;
  customer: { name: string; phone: string }; table_ids: number[] };
type Table = { id: number; code: string; capacity: number };
type Wait = { id: number; earliest: string; latest: string; party_size: number; status: string; notes: string; customer: { name: string; phone: string } };

const NEXT: Record<string, [string, string][]> = {
  held: [["confirmed", "Confirm"], ["cancelled", "Cancel"]],
  confirmed: [["arrived", "Arrived"], ["seated", "Seated"], ["no_show", "No-show"], ["cancelled", "Cancel"]],
  arrived: [["seated", "Seated"], ["completed", "Complete"], ["no_show", "No-show"]],
  seated: [["completed", "Complete"]],
  no_show: [["arrived", "Arrived late"]],
};

export default function ReservationsPage() {
  const { tz, can } = useApp();
  const [day, setDay] = useState(todayIn(tz));
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const list = useApi<Res[]>(`/api/reservations?day=${day}${status ? `&status=${status}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`, 30000);
  const tables = useApi<{ tables: Table[] }>("/api/tables");
  const waitlist = useApi<Wait[]>(`/api/waitlist?day=${day}`, 30000);
  const codes = useMemo(() => Object.fromEntries((tables.data?.tables ?? []).map((t) => [t.id, t.code])), [tables.data]);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Res | null>(null);
  const [addingWait, setAddingWait] = useState(false);
  const act = useAction();

  async function move(r: Res, to: string) {
    let reason = "";
    if (to === "cancelled") {
      const v = window.prompt(`Cancel ${r.ref}? Reason (sent to the guest):`, "cancelled by restaurant");
      if (v === null) return;
      reason = v;
    }
    await act.run(() => api(`/api/reservations/${r.ref}/status`, { method: "POST", body: { status: to, reason } }));
    list.reload();
    waitlist.reload();
  }

  const covers = (list.data ?? []).filter((r) => !["cancelled", "no_show"].includes(r.status)).reduce((s, r) => s + r.party_size, 0);

  return (
    <div>
      <PageHeader title="Reservations">
        <input type="date" className="input w-40" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" />
        <select className="input w-40" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          {["held", "confirmed", "arrived", "seated", "completed", "cancelled", "no_show"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </select>
        <input className="input w-44" placeholder="Search name, phone, ref" value={q} onChange={(e) => setQ(e.target.value)} />
        {can("reservations.manage") && <button className="btn" onClick={() => setCreating(true)}>New reservation</button>}
      </PageHeader>
      <ErrorText error={list.error || act.error} />
      <div className="card overflow-x-auto p-0">
        <table className="table">
          <thead><tr><th>Time</th><th>Guest</th><th>Party</th><th>Table</th><th>Status</th><th>Source</th><th></th></tr></thead>
          <tbody>
            {list.data?.map((r) => (
              <tr key={r.ref}>
                <td className="whitespace-nowrap">{fmtTime(r.starts_at, tz)}<div className="text-xs text-stone-500">{r.ref}</div></td>
                <td>{r.customer.name || "-"}<div className="text-xs text-stone-500">{r.customer.phone}</div>
                  {r.notes && <div className="text-xs text-stone-600">“{r.notes}”</div>}
                  {r.staff_notes && <div className="text-xs text-indigo-700">Staff: {r.staff_notes}</div>}</td>
                <td>{r.party_size}</td>
                <td>{r.table_ids.map((t) => codes[t]).join(" + ") || "-"}</td>
                <td><Badge status={r.status} />
                  {r.status === "held" && <div className="text-xs text-amber-700">{r.hold_reason === "deposit" ? `deposit ${rupees(r.deposit_paise)}` : "waitlist offer"} · until {fmtTime(r.hold_expires_at, tz)}</div>}</td>
                <td className="text-xs">{r.source}</td>
                <td className="whitespace-nowrap text-right">
                  {(NEXT[r.status] ?? []).filter(([to]) => can(to === "cancelled" || to === "confirmed" ? "reservations.manage" : "reservations.arrival")).map(([to, text]) => (
                    <button key={to} className={to === "cancelled" ? "btn-ghost ml-1 text-red-700" : "btn-ghost ml-1"} disabled={act.busy} onClick={() => move(r, to)}>{text}</button>
                  ))}
                  {can("reservations.manage") && ["held", "confirmed"].includes(r.status) && <button className="btn-ghost ml-1" onClick={() => setEditing(r)}>Edit</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.length === 0 && <Empty text="No reservations for this day." />}
      </div>
      <p className="mt-2 text-sm text-stone-500">{list.data?.length ?? 0} bookings · {covers} guests</p>

      <div className="mt-6 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Waitlist</h2>
        {can("waitlist.manage") && <button className="btn-ghost" onClick={() => setAddingWait(true)}>Add to waitlist</button>}
      </div>
      <div className="card mt-2 p-0">
        <table className="table">
          <thead><tr><th>Guest</th><th>Party</th><th>Window</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {waitlist.data?.map((w) => (
              <tr key={w.id}>
                <td>{w.customer.name || "-"}<div className="text-xs text-stone-500">{w.customer.phone}</div></td>
                <td>{w.party_size}</td>
                <td>{fmtTime(w.earliest, tz)} – {fmtTime(w.latest, tz)}</td>
                <td><Badge status={w.status} /></td>
                <td className="text-right">{can("waitlist.manage") && ["waiting", "offered"].includes(w.status) &&
                  <button className="btn-ghost" onClick={async () => { await act.run(() => api(`/api/waitlist/${w.id}/cancel`, { method: "POST" })); waitlist.reload(); list.reload(); }}>Remove</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {waitlist.data?.length === 0 && <Empty text="Nobody waiting." />}
      </div>

      {creating && <ReservationForm day={day} tables={tables.data?.tables ?? []} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); list.reload(); }} />}
      {editing && <ReservationForm existing={editing} day={day} tables={tables.data?.tables ?? []} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); }} />}
      {addingWait && <WaitlistForm day={day} onClose={() => setAddingWait(false)} onSaved={() => { setAddingWait(false); waitlist.reload(); list.reload(); }} />}
    </div>
  );
}

function ReservationForm({ existing, day, tables, onClose, onSaved }: { existing?: Res; day: string; tables: Table[]; onClose: () => void; onSaved: () => void }) {
  const { tz } = useApp();
  const startLocal = existing ? `${new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date(existing.starts_at))}T${hhmm(existing.starts_at, tz)}` : "";
  const [phone, setPhone] = useState(existing?.customer.phone ?? "");
  const [name, setName] = useState(existing?.customer.name ?? "");
  const [party, setParty] = useState(existing?.party_size ?? 2);
  const [date, setDate] = useState(existing ? startLocal.slice(0, 10) : day);
  const [time, setTime] = useState(existing ? startLocal.slice(11, 16) : "");
  const [tableIds, setTableIds] = useState<number[]>(existing?.table_ids ?? []);
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [staffNotes, setStaffNotes] = useState(existing?.staff_notes ?? "");
  const [avail, setAvail] = useState<{ times: string[]; options: { label: string; table_ids: number[] }[] } | null>(null);
  const act = useAction();

  useEffect(() => {
    if (!date || party < 1) return;
    api(`/api/reservations/availability?day=${date}&party_size=${party}`).then(setAvail).catch(() => setAvail(null));
  }, [date, party]);

  async function save() {
    const starts_at = `${date}T${time}`;
    const moved = existing && (starts_at !== startLocal || party !== existing.party_size || tableIds.join() !== existing.table_ids.join());
    const saved = await act.run(() => existing
      ? api(`/api/reservations/${existing.ref}`, { method: "PATCH", body: { notes, staff_notes: staffNotes,
          ...(moved ? { starts_at, party_size: party, table_ids: tableIds.length ? tableIds : null } : {}) } })
      : api("/api/reservations", { method: "POST", body: { phone, name, party_size: party, starts_at, notes, table_ids: tableIds.length ? tableIds : null } }));
    if (saved) onSaved();
  }

  return (
    <Modal title={existing ? `Edit ${existing.ref}` : "New reservation"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Phone"><input className="input" value={phone} disabled={!!existing} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" /></Field>
        <Field label="Name"><input className="input" value={name} disabled={!!existing} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Guests"><input className="input" type="number" min={1} value={party} onChange={(e) => setParty(Number(e.target.value))} /></Field>
        <Field label="Date"><input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      <div className="mt-3">
        <span className="label">Time {avail && `(${avail.times.length} free slots)`}</span>
        <div className="flex flex-wrap gap-1">
          {avail?.times.map((t) => {
            const slot = hhmm(t, tz);
            return <button key={t} type="button" onClick={() => setTime(slot)} className={`rounded border px-2 py-1 text-xs ${time === slot ? "border-brand bg-orange-50 text-brand" : "border-stone-300"}`}>{slot}</button>;
          })}
          {avail?.times.length === 0 && <span className="text-sm text-stone-500">No free tables that day for {party}.</span>}
        </div>
        <input className="input mt-2 w-32" type="time" value={time} onChange={(e) => setTime(e.target.value)} aria-label="Time" />
      </div>
      <Field label="Tables (optional - leave blank to auto-assign)" className="mt-3">
        <div className="flex flex-wrap gap-1">
          {tables.map((t) => (
            <label key={t.id} className="flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs">
              <input type="checkbox" checked={tableIds.includes(t.id)} onChange={(e) => setTableIds(e.target.checked ? [...tableIds, t.id] : tableIds.filter((x) => x !== t.id))} />
              {t.code} ({t.capacity})
            </label>
          ))}
        </div>
      </Field>
      <Field label="Guest requests" className="mt-3"><input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      {existing && <Field label="Staff notes" className="mt-3"><input className="input" value={staffNotes} onChange={(e) => setStaffNotes(e.target.value)} /></Field>}
      <div className="mt-4 space-y-2">
        <ErrorText error={act.error} />
        <button className="btn" disabled={act.busy || !time || (!existing && !phone)} onClick={save}>{existing ? "Save changes" : "Book table"}</button>
      </div>
    </Modal>
  );
}

function WaitlistForm({ day, onClose, onSaved }: { day: string; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ phone: "", name: "", party_size: 2, earliest: "19:00", latest: "21:00", notes: "" });
  const act = useAction();
  return (
    <Modal title="Add to waitlist" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Guests"><input className="input" type="number" min={1} value={f.party_size} onChange={(e) => setF({ ...f, party_size: Number(e.target.value) })} /></Field>
        <div />
        <Field label="Earliest"><input className="input" type="time" value={f.earliest} onChange={(e) => setF({ ...f, earliest: e.target.value })} /></Field>
        <Field label="Latest"><input className="input" type="time" value={f.latest} onChange={(e) => setF({ ...f, latest: e.target.value })} /></Field>
      </div>
      <p className="mt-2 text-xs text-stone-500">When a suitable table frees up, the guest is offered it on WhatsApp and must confirm in time.</p>
      <div className="mt-4 space-y-2">
        <ErrorText error={act.error} />
        <button className="btn" disabled={act.busy || !f.phone} onClick={async () => {
          if (await act.run(() => api("/api/waitlist", { method: "POST", body: { ...f, earliest: `${day}T${f.earliest}`, latest: `${day}T${f.latest}` } }))) onSaved();
        }}>Add</button>
      </div>
    </Modal>
  );
}
