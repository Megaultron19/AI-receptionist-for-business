"use client";
import { useState } from "react";
import { today } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Booking, BookingForm, BookingTable } from "@/components/Bookings";
import { ErrorBox, Header } from "@/components/ui";
import { StartCard } from "@/components/StartCard";

export default function TodayPage() {
  const list = useApi<Booking[]>(`/api/reservations?day=${today()}`, 30000);
  const [adding, setAdding] = useState(false);
  const active = (list.data ?? []).filter((b) => b.status === "confirmed" || b.status === "arrived");
  return (
    <div>
      <StartCard />
      <Header title="Today">
        <span className="text-sm text-stone-500">{active.length} bookings, {active.reduce((n, b) => n + b.guests, 0)} guests</span>
        <button className="btn" onClick={() => setAdding(true)}>New booking</button>
      </Header>
      <ErrorBox text={list.error} />
      <BookingTable rows={list.data ?? []} onChange={list.reload} />
      {adding && <BookingForm onClose={() => setAdding(false)} onSaved={() => { setAdding(false); list.reload(); }} />}
    </div>
  );
}
