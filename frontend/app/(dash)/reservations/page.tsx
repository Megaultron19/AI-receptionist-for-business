"use client";
import { useState } from "react";
import { api, time, today } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Booking, BookingForm, BookingTable } from "@/components/Bookings";
import { ErrorBox, Header } from "@/components/ui";

export default function ReservationsPage() {
  const [day, setDay] = useState(today());
  const [q, setQ] = useState("");
  const list = useApi<Booking[]>(q ? `/api/reservations?q=${encodeURIComponent(q)}` : `/api/reservations?day=${day}`);
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <Header title="Reservations">
        <input className="input w-40" type="date" aria-label="Day" value={day} onChange={(e) => { setQ(""); setDay(e.target.value); }} />
        <input className="input w-52" placeholder="Search name, phone or ref" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn" onClick={() => setAdding(true)}>New booking</button>
      </Header>
      <ErrorBox text={list.error} />
      <BookingTable rows={list.data ?? []} onChange={list.reload} showDate={!!q} />
      <Waitlist />
      {adding && <BookingForm onClose={() => setAdding(false)} onSaved={() => { setAdding(false); list.reload(); }} />}
    </div>
  );
}

type Entry = { id: number; name: string; phone: string; guests: number; wanted_at: string; status: string };

function Waitlist() {
  const list = useApi<Entry[]>("/api/waitlist", 30000);
  if (!list.data?.length) return null;
  return (
    <section className="mt-6">
      <h2 className="mb-2 font-semibold">Waitlist</h2>
      <div className="card p-0">
        <table className="table-list">
          <thead><tr><th>Wants</th><th>Name</th><th>Phone</th><th>Guests</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {list.data.map((e) => (
              <tr key={e.id}>
                <td>{e.wanted_at.slice(5, 10)} {time(e.wanted_at)}</td><td>{e.name}</td><td>{e.phone}</td><td>{e.guests}</td>
                <td>{e.status === "offered" ? "Told a table is free" : "Waiting"}</td>
                <td><button className="btn-light" onClick={async () => { await api(`/api/waitlist/${e.id}`, "DELETE"); list.reload(); }}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
