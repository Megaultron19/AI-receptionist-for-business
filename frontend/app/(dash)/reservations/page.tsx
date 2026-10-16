"use client";
import { useState } from "react";
import { today } from "@/lib/api";
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
      {adding && <BookingForm onClose={() => setAdding(false)} onSaved={() => { setAdding(false); list.reload(); }} />}
    </div>
  );
}
