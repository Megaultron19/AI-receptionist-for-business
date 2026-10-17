"use client";
import { useState } from "react";
import { api, time } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, Field, Header, Modal, useAction } from "@/components/ui";

type Line = { menu_item_id: number | null; name?: string; price?: number; qty: number; notes: string };
type Order = {
  ref: string; name: string; phone: string; status: string; payment_status: string; total: number; source: string;
  booking: string | null; booking_at: string | null; table: string | null; start_by: string | null; ready_note: string; items: Line[];
};
type Dish = { id: number; name: string; price: number; available: boolean };

const NEXT: Record<string, string> = { confirmed: "preparing", preparing: "ready", ready: "served" };
const LABEL: Record<string, string> = { preparing: "Start preparing", ready: "Mark ready", served: "Mark served" };

export default function OrdersPage() {
  const [day, setDay] = useState("");
  const orders = useApi<Order[]>(day ? `/api/orders?day=${day}` : "/api/orders", 15000);
  const [editing, setEditing] = useState<Order | "new" | null>(null);
  const act = useAction();

  async function run(path: string) {
    await act.run(() => api(path, "POST"));
    orders.reload();
  }

  return (
    <div>
      <Header title={day ? "Orders" : "Open orders"}>
        <input type="date" className="input w-auto" value={day} onChange={(e) => setDay(e.target.value)} />
        {day && <button className="btn-light" onClick={() => setDay("")}>Open orders</button>}
        <button className="btn" onClick={() => setEditing("new")}>New order</button>
      </Header>
      <ErrorBox text={orders.error || act.error} />
      <div className="grid gap-3 md:grid-cols-2">
        {orders.data?.map((o) => (
          <div key={o.ref} className={`card ${o.status === "cancelled" ? "opacity-50" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <b>{o.name}</b> <span className="text-sm text-stone-500">#{o.ref}</span>
                <div className="text-xs text-stone-500">
                  {o.booking ? `Booking ${o.booking} at ${time(o.booking_at!)}${o.table ? `, table ${o.table}` : ""}` : "No booking"}
                  {o.start_by && o.status === "confirmed" && <span className="font-medium text-orange-700"> Start by {time(o.start_by)}</span>}
                </div>
              </div>
              <div className="text-right text-xs">
                <div className="font-medium capitalize">{o.status}</div>
                <div className={o.payment_status === "paid" ? "text-green-700" : "text-red-700"}>{o.payment_status}</div>
              </div>
            </div>
            <ul className="my-3 space-y-0.5 text-sm">
              {o.items.map((i, n) => (
                <li key={n} className="flex justify-between">
                  <span>{i.qty} x {i.name}{i.notes && <span className="text-stone-500"> ({i.notes})</span>}</span>
                  <span>₹{i.price! * i.qty}</span>
                </li>
              ))}
              <li className="flex justify-between border-t border-stone-100 pt-1 font-semibold"><span>Total</span><span>₹{o.total}</span></li>
            </ul>
            <div className="flex flex-wrap gap-1">
              {NEXT[o.status] && <button className="btn" onClick={() => run(`/api/orders/${o.ref}/status?status=${NEXT[o.status]}`)}>{LABEL[NEXT[o.status]]}</button>}
              {o.status === "open" && <button className="btn" onClick={() => run(`/api/orders/${o.ref}/status?status=confirmed`)}>Confirm</button>}
              {o.payment_status !== "paid" && o.status !== "cancelled" && <button className="btn-light" onClick={() => run(`/api/orders/${o.ref}/paid`)}>Mark paid</button>}
              {o.payment_status !== "paid" && ["open", "confirmed"].includes(o.status) && <>
                <button className="btn-light" onClick={() => setEditing(o)}>Edit</button>
                <button className="btn-light" onClick={() => window.confirm(`Cancel order ${o.ref}?`) && run(`/api/orders/${o.ref}/status?status=cancelled`)}>Cancel</button>
              </>}
            </div>
          </div>
        ))}
      </div>
      {orders.data?.length === 0 && <p className="card text-center text-sm text-stone-500">No orders.</p>}
      {editing && <OrderForm order={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); orders.reload(); }} />}
    </div>
  );
}

function OrderForm({ order, onClose, onSaved }: { order: Order | null; onClose: () => void; onSaved: () => void }) {
  const menu = useApi<Dish[]>("/api/menu");
  const [f, setF] = useState({ name: "", phone: "", booking: "" });
  const [lines, setLines] = useState<Line[]>(order ? order.items : [{ menu_item_id: null, qty: 1, notes: "" }]);
  const act = useAction();
  const dishes = (menu.data ?? []).filter((d) => d.available || lines.some((l) => l.menu_item_id === d.id));
  const price = Object.fromEntries((menu.data ?? []).map((d) => [d.id, d.price]));
  const ready = lines.length > 0 && lines.every((l) => l.menu_item_id && l.qty > 0) && (order || f.name);
  const setLine = (n: number, change: Partial<Line>) => setLines(lines.map((l, i) => (i === n ? { ...l, ...change } : l)));

  async function save() {
    const items = lines.map((l) => ({ menu_item_id: l.menu_item_id, qty: l.qty, notes: l.notes }));
    const done = await act.run(() => order ? api(`/api/orders/${order.ref}/items`, "PUT", items) : api("/api/orders", "POST", { ...f, items }));
    if (done) onSaved();
  }

  return (
    <Modal title={order ? `Edit order ${order.ref}` : "New order"} onClose={onClose}>
      {!order && (
        <div className="mb-3 grid grid-cols-3 gap-2">
          <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
          <Field label="Booking ref"><input className="input" value={f.booking} onChange={(e) => setF({ ...f, booking: e.target.value })} placeholder="optional" /></Field>
        </div>
      )}
      <div className="space-y-2">
        {lines.map((l, n) => (
          <div key={n} className="flex gap-1">
            <select className="input" value={l.menu_item_id ?? ""} onChange={(e) => setLine(n, { menu_item_id: Number(e.target.value) || null })}>
              <option value="">Choose a dish</option>
              {dishes.map((d) => <option key={d.id} value={d.id}>{d.name} (₹{d.price})</option>)}
            </select>
            <input className="input w-16" type="number" min={1} max={20} value={l.qty} onChange={(e) => setLine(n, { qty: Number(e.target.value) })} />
            <input className="input" placeholder="Notes" value={l.notes} onChange={(e) => setLine(n, { notes: e.target.value })} />
            <button className="btn-light" aria-label="Remove" onClick={() => setLines(lines.filter((_, i) => i !== n))}>✕</button>
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between">
        <button className="btn-light" onClick={() => setLines([...lines, { menu_item_id: null, qty: 1, notes: "" }])}>Add dish</button>
        <b>Total ₹{lines.reduce((sum, l) => sum + (l.menu_item_id ? price[l.menu_item_id] ?? 0 : 0) * l.qty, 0)}</b>
      </div>
      <div className="mt-4"><button className="btn" disabled={act.busy || !ready} onClick={save}>Save</button></div>
      <div className="mt-2"><ErrorBox text={act.error || menu.error} /></div>
    </Modal>
  );
}
