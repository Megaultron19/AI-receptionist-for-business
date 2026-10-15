"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime, fmtTime, rupees, todayIn } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { Badge, Empty, ErrorText, Field, Modal, PageHeader, useAction } from "@/components/ui";
import { BillView, Line, Order } from "@/components/Bill";

const GROUPS: [string, string][] = [
  ["submitted", "To accept"], ["accepted,preparing", "In kitchen"], ["ready", "Ready"],
  ["draft,awaiting_payment,payment_pending", "Awaiting payment"], ["completed,cancelled,refunded", "Done"],
];

export default function OrdersPage() {
  const { tz, can } = useApp();
  const [group, setGroup] = useState(GROUPS[0][0]);
  const list = useApi<Order[]>(`/api/orders?status=${group}`, 15000);
  const [detail, setDetail] = useState<string | null>(null);
  const [building, setBuilding] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const act = useAction();

  async function step(o: Order, status: string) {
    let eta: number | null = null, reason = "";
    if (status === "accepted") {
      const v = window.prompt(`Accept ${o.ref}. Minutes until ready?`, String(o.estimate_minutes ?? 10));
      if (v === null) return;
      eta = Number(v);
    }
    if (status === "cancelled") {
      const v = window.prompt(`Reject/cancel ${o.ref}? Reason for the customer:`, "item unavailable");
      if (v === null) return;
      reason = v;
    }
    await act.run(() => api(`/api/orders/${o.ref}/status`, { method: "POST", body: { status, eta_minutes: eta, reason } }));
    list.reload();
  }

  return (
    <div>
      <PageHeader title="Orders">
        {can("orders.manage") && <button className="btn" onClick={() => setCreating(true)}>New phone order</button>}
      </PageHeader>
      <div className="mb-3 flex flex-wrap gap-1">
        {GROUPS.map(([g, name]) => <button key={g} onClick={() => setGroup(g)} className={group === g ? "btn" : "btn-ghost"}>{name}</button>)}
      </div>
      <ErrorText error={list.error || act.error} />
      <div className="grid gap-3 md:grid-cols-2">
        {list.data?.map((o) => (
          <div key={o.ref} className="card">
            <div className="flex items-start justify-between">
              <div>
                <button className="font-semibold text-brand underline" onClick={() => setDetail(o.ref)}>{o.ref}</button> <Badge status={o.status} />
                <div className="text-sm">{o.customer.name || "-"} · {o.customer.phone}</div>
                <div className="text-xs text-stone-500">{o.order_type === "pickup" ? "Pickup" : "Dine-in"} · {o.scheduled_for ? `for ${fmtTime(o.scheduled_for, tz)}` : "ASAP"} · via {o.channel} · {fmtDateTime(o.created_at, tz)}</div>
              </div>
              <div className="text-right"><div className="font-semibold">{rupees(o.total_paise)}</div>
                <div className="text-xs text-stone-500">paid {rupees(o.amount_paid_paise)}</div></div>
            </div>
            <ul className="mt-2 text-sm">{o.items.map((l) => <li key={l.id}>{l.quantity} × {l.item_name}{l.variant_name && ` (${l.variant_name})`}{l.addons.length > 0 && ` + ${l.addons.map((a) => a.name).join(", ")}`}{l.instructions && <i className="text-stone-500"> - {l.instructions}</i>}</li>)}</ul>
            {o.estimated_ready_at && <div className="mt-1 text-xs text-sky-700">Ready by {fmtTime(o.estimated_ready_at, tz)}</div>}
            {o.cancel_reason && <div className="mt-1 text-xs text-red-700">{o.cancel_reason}</div>}
            <div className="mt-3 flex flex-wrap gap-1">
              {o.status === "submitted" && <button className="btn" onClick={() => step(o, "accepted")}>Accept</button>}
              {o.status === "accepted" && <button className="btn-ghost" onClick={() => step(o, "preparing")}>Start preparing</button>}
              {["accepted", "preparing"].includes(o.status) && <button className="btn" onClick={() => step(o, "ready")}>Mark ready</button>}
              {o.status === "ready" && <button className="btn" onClick={() => step(o, "completed")}>Handed over</button>}
              {o.status === "draft" && can("orders.manage") && <button className="btn-ghost" onClick={() => setBuilding(o.ref)}>Continue order</button>}
              {can("orders.manage") && ["draft", "awaiting_payment", "payment_pending", "submitted", "accepted", "preparing"].includes(o.status) &&
                <button className="btn-ghost text-red-700" onClick={() => step(o, "cancelled")}>{o.status === "submitted" ? "Reject" : "Cancel"}</button>}
            </div>
          </div>
        ))}
      </div>
      {list.data?.length === 0 && <div className="card"><Empty text="No orders here." /></div>}
      {detail && <OrderDetail orderRef={detail} onClose={() => setDetail(null)} />}
      {creating && <NewOrder onClose={() => setCreating(false)} onCreated={(ref) => { setCreating(false); setBuilding(ref); }} />}
      {building && <OrderBuilder orderRef={building} onClose={() => { setBuilding(null); list.reload(); }} />}
    </div>
  );
}

function OrderDetail({ orderRef, onClose }: { orderRef: string; onClose: () => void }) {
  const { tz } = useApp();
  const o = useApi<Order>(`/api/orders/${orderRef}`);
  const [invoice, setInvoice] = useState<any>(null);
  const act = useAction();
  return (
    <Modal title={`Order ${orderRef}`} onClose={onClose}>
      <ErrorText error={o.error || act.error} />
      {o.data && (
        <div className="space-y-3">
          <div><Badge status={o.data.status} /> <span className="text-sm">{o.data.customer.name} · {o.data.customer.phone}</span></div>
          {o.data.special_instructions && <p className="text-sm">Note: {o.data.special_instructions}</p>}
          <BillView bill={o.data.bill} />
          {o.data.quote && <p className="text-xs text-stone-500">Kitchen estimate now: {o.data.quote.estimate_minutes} min (target {o.data.quote.target_minutes}) {o.data.quote.reasons.join("; ")}</p>}
          <div>
            <h3 className="text-sm font-semibold">Payments</h3>
            {o.data.payments.length === 0 && <p className="text-sm text-stone-500">None.</p>}
            {o.data.payments.map((p) => <div key={p.ref} className="text-sm">{p.ref} · {rupees(p.amount_paise)} · <Badge status={p.status} />{p.refunded_paise > 0 && ` refunded ${rupees(p.refunded_paise)}`}</div>)}
          </div>
          {o.data.invoice_number && <button className="btn-ghost" onClick={() => act.run(async () => setInvoice(await api(`/api/orders/${orderRef}/invoice`)))}>View invoice {o.data.invoice_number}</button>}
          {invoice && <Invoice inv={invoice} tz={tz} />}
        </div>
      )}
    </Modal>
  );
}

function Invoice({ inv, tz }: { inv: any; tz: string }) {
  return (
    <div className="rounded border border-stone-300 p-4 text-sm print:border-0" id="invoice">
      <div className="flex justify-between">
        <div><b>{inv.seller.name}</b>{inv.seller.trade_name !== inv.seller.name && <div>{inv.seller.trade_name}</div>}<div>{inv.seller.address}, {inv.seller.city} {inv.seller.pincode}</div>
          <div>GSTIN: {inv.seller.gstin || "-"} · State code {inv.seller.state_code || "-"}</div>{inv.seller.fssai && <div>FSSAI: {inv.seller.fssai}</div>}</div>
        <div className="text-right"><b>Tax invoice</b><div>{inv.invoice_number}</div><div>{fmtDateTime(inv.date, tz)}</div><div>Order {inv.order_ref}</div></div>
      </div>
      <div className="mt-2">Bill to: {inv.buyer.name || "Customer"} · {inv.buyer.phone}{inv.buyer.gstin && ` · GSTIN ${inv.buyer.gstin}`}</div>
      <div className="text-xs text-stone-500">Place of supply: {inv.place_of_supply || "-"} · SAC {inv.sac}</div>
      <BillView bill={inv.bill} />
      <div className="mt-1">Paid: {rupees(inv.amount_paid_paise)}</div>
      <button className="btn-ghost mt-2 print:hidden" onClick={() => window.print()}>Print</button>
    </div>
  );
}

function NewOrder({ onClose, onCreated }: { onClose: () => void; onCreated: (ref: string) => void }) {
  const [f, setF] = useState({ phone: "", name: "", order_type: "pickup", special_instructions: "" });
  const act = useAction();
  return (
    <Modal title="New phone order" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Type"><select className="input" value={f.order_type} onChange={(e) => setF({ ...f, order_type: e.target.value })}><option value="pickup">Pickup</option><option value="dine_in">Dine-in</option></select></Field>
        <Field label="Note"><input className="input" value={f.special_instructions} onChange={(e) => setF({ ...f, special_instructions: e.target.value })} /></Field>
      </div>
      <div className="mt-4 space-y-2"><ErrorText error={act.error} />
        <button className="btn" disabled={act.busy || !f.phone} onClick={async () => { const o = await act.run(() => api<Order>("/api/orders", { method: "POST", body: f })); if (o) onCreated(o.ref); }}>Start order</button></div>
    </Modal>
  );
}

type MenuItem = { id: number; name: string; category: string; available: boolean; price_paise: number; variants: { id: number; name: string; price_paise: number; available: boolean }[];
  addon_groups: { id: number; name: string; min_select: number; max_select: number; addons: { id: number; name: string; price_paise: number; available: boolean }[] }[] };

function OrderBuilder({ orderRef, onClose }: { orderRef: string; onClose: () => void }) {
  const { tz } = useApp();
  const o = useApi<Order>(`/api/orders/${orderRef}`);
  const menu = useApi<{ items: MenuItem[] }>("/api/menu");
  const [itemId, setItemId] = useState<number | "">("");
  const [variant, setVariant] = useState<number | null>(null);
  const [addons, setAddons] = useState<number[]>([]);
  const [qty, setQty] = useState(1);
  const [instr, setInstr] = useState("");
  const [when, setWhen] = useState("");
  const [gstin, setGstin] = useState("");
  const act = useAction();
  const item = menu.data?.items.find((i) => i.id === itemId);

  async function add() {
    const out = await act.run(() => api<Order>(`/api/orders/${orderRef}/items`, { method: "POST", body: { menu_item_id: itemId, quantity: qty, variant_id: variant, addon_ids: addons, instructions: instr } }));
    if (out) { o.setData(out); setItemId(""); setVariant(null); setAddons([]); setQty(1); setInstr(""); }
  }
  async function change(line: Line, quantity: number) {
    const out = await act.run(() => quantity === 0 ? api<Order>(`/api/orders/${orderRef}/items/${line.id}`, { method: "DELETE" })
      : api<Order>(`/api/orders/${orderRef}/items/${line.id}`, { method: "PATCH", body: { quantity } }));
    if (out) o.setData(out);
  }
  async function confirm() {
    const today = todayIn(tz);
    const out = await act.run(() => api<Order>(`/api/orders/${orderRef}/confirm`, { method: "POST", body: { scheduled_for: when ? `${today}T${when}` : null, customer_gstin: gstin } }));
    if (out) onClose();
  }

  return (
    <Modal title={`Order ${orderRef}`} onClose={onClose}>
      <div className="grid gap-2 md:grid-cols-2">
        <Field label="Dish"><select className="input" value={itemId} onChange={(e) => { setItemId(Number(e.target.value)); setVariant(null); setAddons([]); }}>
          <option value="">Choose…</option>
          {menu.data?.items.map((i) => <option key={i.id} value={i.id} disabled={!i.available}>{i.category}: {i.name}{!i.available ? " (out of stock)" : i.variants.length ? "" : ` - ${rupees(i.price_paise)}`}</option>)}
        </select></Field>
        <Field label="Quantity"><input className="input" type="number" min={1} max={50} value={qty} onChange={(e) => setQty(Number(e.target.value))} /></Field>
      </div>
      {item && item.variants.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">{item.variants.map((v) => (
          <button key={v.id} disabled={!v.available} onClick={() => setVariant(v.id)} className={`rounded border px-2 py-1 text-xs ${variant === v.id ? "border-brand bg-orange-50" : "border-stone-300"}`}>{v.name} {rupees(v.price_paise)}</button>))}</div>
      )}
      {item?.addon_groups.map((g) => (
        <div key={g.id} className="mt-2"><span className="label">{g.name} (choose {g.min_select === g.max_select ? g.min_select : `${g.min_select}–${g.max_select}`})</span>
          <div className="flex flex-wrap gap-1">{g.addons.map((a) => (
            <label key={a.id} className="flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs">
              <input type="checkbox" disabled={!a.available} checked={addons.includes(a.id)} onChange={(e) => setAddons(e.target.checked ? [...addons, a.id] : addons.filter((x) => x !== a.id))} />
              {a.name}{a.price_paise ? ` +${rupees(a.price_paise)}` : ""}</label>))}</div></div>
      ))}
      {item && <div className="mt-2 flex gap-2"><input className="input" placeholder="Instructions (optional)" value={instr} onChange={(e) => setInstr(e.target.value)} />
        <button className="btn" disabled={act.busy} onClick={add}>Add</button></div>}
      <ErrorText error={act.error || o.error} />
      {o.data && (
        <div className="mt-4">
          {o.data.items.map((l) => (
            <div key={l.id} className="flex items-center justify-between border-b border-stone-100 py-1 text-sm">
              <span>{l.item_name}{l.variant_name && ` (${l.variant_name})`}{l.addons.length > 0 && ` + ${l.addons.map((a) => a.name).join(", ")}`}</span>
              <span className="flex items-center gap-1">
                <button className="btn-ghost px-2 py-0" onClick={() => change(l, l.quantity - 1)}>−</button>{l.quantity}
                <button className="btn-ghost px-2 py-0" onClick={() => change(l, l.quantity + 1)}>+</button>
                <span className="w-20 text-right">{rupees(l.line_total_paise)}</span></span>
            </div>
          ))}
          {o.data.items.length > 0 && <BillView bill={o.data.bill} />}
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Field label="Pickup time today (blank = ASAP)"><input className="input" type="time" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
            <Field label="Customer GSTIN (optional)"><input className="input" value={gstin} onChange={(e) => setGstin(e.target.value)} /></Field>
          </div>
          <button className="btn mt-3" disabled={act.busy || o.data.items.length === 0} onClick={confirm}>
            Confirm{o.data.amount_due_paise ? ` & send ${rupees(o.data.amount_due_paise)} payment link` : " & send to kitchen"}
          </button>
        </div>
      )}
    </Modal>
  );
}
