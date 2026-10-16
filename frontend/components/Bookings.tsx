"use client";
import { useEffect, useState } from "react";
import { api, ApiError, time, today } from "@/lib/api";
import { ErrorBox, Field, Modal, useAction } from "./ui";

export type Booking = { ref: string; name: string; phone: string; guests: number; starts_at: string; status: string; table: string | null; source: string; notes: string };

const ACTIONS: Record<string, [string, string][]> = {
  confirmed: [["arrived", "Arrived"], ["no_show", "No-show"], ["cancelled", "Cancel"]],
  arrived: [["completed", "Done"]],
  no_show: [["arrived", "Arrived late"]],
};

const COLORS: Record<string, string> = {
  confirmed: "bg-green-100 text-green-800", arrived: "bg-sky-100 text-sky-800", completed: "bg-stone-200 text-stone-600",
  cancelled: "bg-red-100 text-red-700", no_show: "bg-red-100 text-red-700",
};

export function BookingTable({ rows, onChange, showDate = false }: { rows: Booking[]; onChange: () => void; showDate?: boolean }) {
  const act = useAction();
  const [editing, setEditing] = useState<Booking | null>(null);

  async function move(b: Booking, status: string) {
    if (status === "cancelled" && !window.confirm(`Cancel booking ${b.ref} for ${b.name}?`)) return;
    await act.run(() => api(`/api/reservations/${b.ref}/status?status=${status}`, "POST"));
    onChange();
  }

  return (
    <div className="card overflow-x-auto p-0">
      <ErrorBox text={act.error} />
      <table className="table-list">
        <thead><tr><th>Time</th><th>Guest</th><th>Guests</th><th>Table</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.ref}>
              <td>{showDate && <div className="text-xs text-stone-500">{b.starts_at.slice(0, 10)}</div>}{time(b.starts_at)}<div className="text-xs text-stone-500">{b.ref}</div></td>
              <td>{b.name}<div className="text-xs text-stone-500">{b.phone}</div>{b.notes && <div className="text-xs">{b.notes}</div>}</td>
              <td>{b.guests}</td>
              <td>{b.table ?? "-"}</td>
              <td><span className={`rounded px-2 py-0.5 text-xs ${COLORS[b.status] ?? ""}`}>{b.status.replace("_", " ")}</span></td>
              <td className="whitespace-nowrap text-right">
                {(ACTIONS[b.status] ?? []).map(([s, label]) => <button key={s} className="btn-light ml-1" disabled={act.busy} onClick={() => move(b, s)}>{label}</button>)}
                {b.status === "confirmed" && <button className="btn-light ml-1" onClick={() => setEditing(b)}>Change</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="p-6 text-center text-sm text-stone-500">No bookings.</p>}
      {editing && <BookingForm existing={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); onChange(); }} />}
    </div>
  );
}

export function BookingForm({ existing, onClose, onSaved }: { existing?: Booking; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(existing?.name ?? "");
  const [phone, setPhone] = useState(existing?.phone ?? "");
  const [guests, setGuests] = useState(existing?.guests ?? 2);
  const [day, setDay] = useState(existing?.starts_at.slice(0, 10) ?? today());
  const [slot, setSlot] = useState(existing ? time(existing.starts_at) : "");
  const [slots, setSlots] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (guests > 0) api<string[]>(`/api/reservations/availability?day=${day}&guests=${guests}`).then(setSlots).catch(() => setSlots([]));
  }, [day, guests]);

  async function save() {
    setError("");
    try {
      const starts_at = `${day}T${slot}:00`;
      if (existing) await api(`/api/reservations/${existing.ref}`, "PUT", { guests, starts_at });
      else await api("/api/reservations", "POST", { name, phone, guests, starts_at });
      onSaved();
    } catch (e: any) {
      const alts = e instanceof ApiError && e.alternatives.length ? ` Free nearby: ${e.alternatives.map(time).join(", ")}` : "";
      setError(e.message + alts);
    }
  }

  return (
    <Modal title={existing ? `Change ${existing.ref}` : "New booking"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"><input className="input" value={name} disabled={!!existing} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Phone"><input className="input" value={phone} disabled={!!existing} onChange={(e) => setPhone(e.target.value)} /></Field>
        <Field label="Guests"><input className="input" type="number" min={1} value={guests} onChange={(e) => setGuests(Number(e.target.value))} /></Field>
        <Field label="Date"><input className="input" type="date" value={day} onChange={(e) => setDay(e.target.value)} /></Field>
      </div>
      <p className="label mt-3">Time</p>
      <div className="flex flex-wrap gap-1">
        {slots.map((s) => <button key={s} onClick={() => setSlot(s)} className={`rounded border px-2 py-1 text-xs ${slot === s ? "border-orange-700 bg-orange-50" : "border-stone-300"}`}>{s}</button>)}
        {slots.length === 0 && <span className="text-sm text-stone-500">No free tables that day.</span>}
      </div>
      <div className="mt-4 space-y-2">
        <ErrorBox text={error} />
        <button className="btn" disabled={!slot || (!existing && (!name || !phone))} onClick={save}>{existing ? "Save" : "Book"}</button>
      </div>
    </Modal>
  );
}
