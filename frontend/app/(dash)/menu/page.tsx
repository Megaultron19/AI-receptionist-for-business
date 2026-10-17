"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useMe } from "@/components/Shell";
import { ErrorBox, Field, Header, Modal, useAction } from "@/components/ui";

type Item = { id: number; name: string; category: string; description: string; price: number; veg: boolean; available: boolean; prep_minutes: number; other_names: string };
const BLANK: Omit<Item, "id"> = { name: "", category: "", description: "", price: 0, veg: true, available: true, prep_minutes: 10, other_names: "" };

export default function MenuPage() {
  const me = useMe();
  const items = useApi<Item[]>("/api/menu");
  const [editing, setEditing] = useState<Partial<Item> | null>(null);
  const act = useAction();
  const groups = new Map<string, Item[]>();
  for (const i of items.data ?? []) groups.set(i.category || "Other", [...(groups.get(i.category || "Other") ?? []), i]);

  async function toggle(i: Item) {
    await act.run(() => api(`/api/menu/${i.id}/available?available=${!i.available}`, "POST"));
    items.reload();
  }

  return (
    <div>
      <Header title="Menu">{me.role === "owner" && <button className="btn" onClick={() => setEditing(BLANK)}>Add dish</button>}</Header>
      <ErrorBox text={items.error || act.error} />
      {[...groups].map(([category, list]) => (
        <section key={category} className="mb-5">
          <h2 className="mb-2 font-semibold">{category}</h2>
          <div className="card divide-y divide-stone-100 p-0">
            {list.map((i) => (
              <div key={i.id} className="flex items-center justify-between gap-2 p-3">
                <div className={i.available ? "" : "opacity-50"}>
                  <span className={`mr-2 inline-block h-2 w-2 rounded-full ${i.veg ? "bg-green-600" : "bg-red-600"}`} />
                  <b>{i.name}</b> <span className="text-sm">₹{i.price}</span>
                  {i.description && <div className="text-xs text-stone-500">{i.description}</div>}
                </div>
                <div className="flex gap-1">
                  <button className="btn-light" onClick={() => toggle(i)}>{i.available ? "Out of stock" : "Back in stock"}</button>
                  {me.role === "owner" && <button className="btn-light" onClick={() => setEditing(i)}>Edit</button>}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      {items.data?.length === 0 && <p className="card text-center text-sm text-stone-500">No dishes yet.</p>}
      {editing && <ItemForm item={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); items.reload(); }} />}
    </div>
  );
}

function ItemForm({ item, onClose, onSaved }: { item: Partial<Item>; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ ...BLANK, ...item });
  const act = useAction();
  const set = (k: keyof Item, v: unknown) => setF({ ...f, [k]: v });
  return (
    <Modal title={item.id ? `Edit ${item.name}` : "Add dish"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Category"><input className="input" value={f.category} onChange={(e) => set("category", e.target.value)} placeholder="Starters" /></Field>
        <Field label="Price (₹)"><input className="input" type="number" min={1} value={f.price || ""} onChange={(e) => set("price", Number(e.target.value))} /></Field>
        <Field label="Prep time (minutes)"><input className="input" type="number" min={0} value={f.prep_minutes} onChange={(e) => set("prep_minutes", Number(e.target.value))} /></Field>
      </div>
      <div className="mt-3 space-y-3">
        <Field label="Description"><input className="input" value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
        <Field label="Other names customers use (comma separated)"><input className="input" value={f.other_names} onChange={(e) => set("other_names", e.target.value)} placeholder="pbm, butter paneer" /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.veg} onChange={(e) => set("veg", e.target.checked)} /> Vegetarian</label>
      </div>
      <div className="mt-4 flex gap-2">
        <button className="btn" disabled={act.busy || !f.name || !f.price} onClick={async () => {
          const body = { name: f.name, category: f.category, description: f.description, price: f.price, veg: f.veg, available: f.available, prep_minutes: f.prep_minutes, other_names: f.other_names };
          if (await act.run(() => item.id ? api(`/api/menu/${item.id}`, "PUT", body) : api("/api/menu", "POST", body))) onSaved();
        }}>Save</button>
        {item.id && <button className="btn-light" onClick={async () => {
          if (window.confirm(`Delete ${item.name}?`) && await act.run(() => api(`/api/menu/${item.id}`, "DELETE"))) onSaved();
        }}>Delete</button>}
      </div>
      <div className="mt-2"><ErrorBox text={act.error} /></div>
    </Modal>
  );
}
