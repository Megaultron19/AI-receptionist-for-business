"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { rupees, toPaise } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { ErrorText, Field, Modal, PageHeader, useAction } from "@/components/ui";

type Category = { id: number; name: string; name_hi: string; sort: number; active: boolean };
type Addon = { id?: number; name: string; price_paise: number; available: boolean };
type Group = { id?: number; name: string; min_select: number; max_select: number; addons: Addon[] };
type Variant = { id?: number; name: string; price_paise: number; available: boolean };
type Item = { id: number; category_id: number; name: string; name_hi: string; aliases: string[]; description: string; price_paise: number; image_url: string;
  dietary: string[]; allergens: string; spice_level: string; available: boolean; prep_minutes: number; tax_rate_bp: number | null; sort: number; variants: Variant[]; addon_groups: Group[] };
const DIETARY = ["veg", "non_veg", "egg", "vegan", "jain", "gluten_free", "contains_nuts", "dairy_free"];

export default function MenuPage() {
  const { can } = useApp();
  const menu = useApi<{ categories: Category[]; items: Item[] }>("/api/menu");
  const [editItem, setEditItem] = useState<Partial<Item> | null>(null);
  const [editCat, setEditCat] = useState<Partial<Category> | null>(null);
  const act = useAction();

  async function toggle(it: Item, target: { variant_id?: number; addon_id?: number }, available: boolean) {
    await act.run(() => api(`/api/menu/items/${it.id}/availability`, { method: "POST", body: { available, ...target } }));
    menu.reload();
  }

  return (
    <div>
      <PageHeader title="Menu">
        {can("menu.manage") && <><button className="btn-ghost" onClick={() => setEditCat({ sort: 0, active: true })}>Add category</button>
          <button className="btn" disabled={!menu.data?.categories.length} onClick={() => setEditItem({ category_id: menu.data!.categories[0].id, available: true, prep_minutes: 10, dietary: [], aliases: [], variants: [], addon_groups: [], sort: 0 })}>Add dish</button></>}
      </PageHeader>
      <ErrorText error={menu.error || act.error} />
      {menu.data?.categories.map((c) => (
        <div key={c.id} className="mb-5">
          <div className="mb-2 flex items-center gap-2"><h2 className={`text-lg font-semibold ${c.active ? "" : "text-stone-400"}`}>{c.name} {c.name_hi && <span className="text-sm text-stone-500">{c.name_hi}</span>}</h2>
            {can("menu.manage") && <button className="text-xs text-brand underline" onClick={() => setEditCat(c)}>edit</button>}</div>
          <div className="card divide-y divide-stone-100 p-0">
            {menu.data!.items.filter((i) => i.category_id === c.id).map((it) => (
              <div key={it.id} className="flex flex-wrap items-start justify-between gap-2 p-3">
                <div className={it.available ? "" : "opacity-50"}>
                  <div className="font-medium">{it.name} {it.name_hi && <span className="text-sm text-stone-500">{it.name_hi}</span>}
                    {it.dietary.includes("veg") && <span className="ml-1 text-xs text-green-700">● veg</span>}{it.dietary.includes("non_veg") && <span className="ml-1 text-xs text-red-700">● non-veg</span>}</div>
                  <div className="text-sm text-stone-600">{it.variants.length ? it.variants.map((v) => `${v.name} ${rupees(v.price_paise)}${v.available ? "" : " (out)"}`).join(" · ") : rupees(it.price_paise)} · {it.prep_minutes} min</div>
                  {it.allergens && <div className="text-xs text-stone-500">Allergens: {it.allergens}</div>}
                  {it.addon_groups.map((g) => <div key={g.id} className="text-xs text-stone-500">{g.name}: {g.addons.map((a) => (
                    <button key={a.id} disabled={!can("menu.availability")} onClick={() => toggle(it, { addon_id: a.id }, !a.available)} className={`mr-1 ${a.available ? "" : "line-through"}`}>{a.name}</button>))}</div>)}
                </div>
                <div className="flex flex-wrap gap-1">
                  {can("menu.availability") && <button className={it.available ? "btn-ghost" : "btn"} onClick={() => toggle(it, {}, !it.available)}>{it.available ? "Mark out of stock" : "Back in stock"}</button>}
                  {can("menu.availability") && it.variants.map((v) => <button key={v.id} className="btn-ghost text-xs" onClick={() => toggle(it, { variant_id: v.id }, !v.available)}>{v.name}: {v.available ? "in" : "out"}</button>)}
                  {can("menu.manage") && <button className="btn-ghost" onClick={() => setEditItem(it)}>Edit</button>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {editCat && <CategoryForm cat={editCat} onClose={() => setEditCat(null)} onSaved={() => { setEditCat(null); menu.reload(); }} />}
      {editItem && <ItemForm item={editItem} categories={menu.data?.categories ?? []} onClose={() => setEditItem(null)} onSaved={() => { setEditItem(null); menu.reload(); }} />}
    </div>
  );
}

function CategoryForm({ cat, onClose, onSaved }: { cat: Partial<Category>; onClose: () => void; onSaved: () => void }) {
  const [c, setC] = useState(cat);
  const act = useAction();
  return (
    <Modal title={cat.id ? "Edit category" : "Add category"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"><input className="input" value={c.name ?? ""} onChange={(e) => setC({ ...c, name: e.target.value })} /></Field>
        <Field label="Hindi name"><input className="input" value={c.name_hi ?? ""} onChange={(e) => setC({ ...c, name_hi: e.target.value })} /></Field>
        <Field label="Sort"><input className="input" type="number" value={c.sort ?? 0} onChange={(e) => setC({ ...c, sort: Number(e.target.value) })} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={c.active ?? true} onChange={(e) => setC({ ...c, active: e.target.checked })} /> Shown on menu</label>
      </div>
      <div className="mt-4 space-y-2"><ErrorText error={act.error} />
        <button className="btn" disabled={act.busy} onClick={async () => {
          const body = { name: c.name, name_hi: c.name_hi ?? "", sort: c.sort ?? 0, active: c.active ?? true };
          if (await act.run(() => api(cat.id ? `/api/menu/categories/${cat.id}` : "/api/menu/categories", { method: cat.id ? "PUT" : "POST", body }))) onSaved();
        }}>Save</button></div>
    </Modal>
  );
}

const money = (p: number) => (p / 100).toFixed(2).replace(/\.00$/, "");

function ItemForm({ item, categories, onClose, onSaved }: { item: Partial<Item>; categories: Category[]; onClose: () => void; onSaved: () => void }) {
  const [it, setIt] = useState<Partial<Item>>(item);
  const [price, setPrice] = useState(item.price_paise ? money(item.price_paise) : "");
  const [variants, setVariants] = useState(item.variants?.map((v) => ({ ...v, price: money(v.price_paise) })) ?? []);
  const [groups, setGroups] = useState(item.addon_groups?.map((g) => ({ ...g, addons: g.addons.map((a) => ({ ...a, price: money(a.price_paise) })) })) ?? []);
  const act = useAction();
  const set = (k: keyof Item, v: any) => setIt({ ...it, [k]: v });

  async function save() {
    const body = await act.run(async () => ({
      category_id: it.category_id, name: it.name, name_hi: it.name_hi ?? "", aliases: (it.aliases ?? []).filter(Boolean), description: it.description ?? "",
      price_paise: price ? toPaise(price) : 0, image_url: it.image_url ?? "", dietary: it.dietary ?? [], allergens: it.allergens ?? "", spice_level: it.spice_level ?? "",
      available: it.available ?? true, prep_minutes: it.prep_minutes ?? 10, tax_rate_bp: it.tax_rate_bp ?? null, sort: it.sort ?? 0,
      variants: variants.map((v) => ({ name: v.name, price_paise: toPaise(v.price), available: v.available })),
      addon_groups: groups.map((g) => ({ name: g.name, min_select: g.min_select, max_select: g.max_select, addons: g.addons.map((a) => ({ name: a.name, price_paise: toPaise(a.price || "0"), available: a.available })) })),
    }));
    if (!body) return;
    if (await act.run(() => api(item.id ? `/api/menu/items/${item.id}` : "/api/menu/items", { method: item.id ? "PUT" : "POST", body }))) onSaved();
  }

  return (
    <Modal title={item.id ? `Edit ${item.name}` : "Add dish"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"><input className="input" value={it.name ?? ""} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Hindi name"><input className="input" value={it.name_hi ?? ""} onChange={(e) => set("name_hi", e.target.value)} /></Field>
        <Field label="Category"><select className="input" value={it.category_id} onChange={(e) => set("category_id", Number(e.target.value))}>{categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Price ₹ (if no sizes)"><input className="input" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="280" /></Field>
        <Field label="Other names customers use (comma-separated)" className="col-span-2"><input className="input" value={(it.aliases ?? []).join(", ")} onChange={(e) => set("aliases", e.target.value.split(",").map((s) => s.trim()))} /></Field>
        <Field label="Description" className="col-span-2"><input className="input" value={it.description ?? ""} onChange={(e) => set("description", e.target.value)} /></Field>
        <Field label="Allergens (as you want customers told)"><input className="input" value={it.allergens ?? ""} onChange={(e) => set("allergens", e.target.value)} /></Field>
        <Field label="Spice level"><input className="input" value={it.spice_level ?? ""} onChange={(e) => set("spice_level", e.target.value)} /></Field>
        <Field label="Prep minutes"><input className="input" type="number" min={0} value={it.prep_minutes ?? 10} onChange={(e) => set("prep_minutes", Number(e.target.value))} /></Field>
        <Field label="GST % override (blank = default)"><input className="input" value={it.tax_rate_bp == null ? "" : it.tax_rate_bp / 100} onChange={(e) => set("tax_rate_bp", e.target.value === "" ? null : Math.round(Number(e.target.value) * 100))} /></Field>
        <Field label="Image URL (https)" className="col-span-2"><input className="input" value={it.image_url ?? ""} onChange={(e) => set("image_url", e.target.value)} /></Field>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">{DIETARY.map((d) => (
        <label key={d} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={(it.dietary ?? []).includes(d)}
          onChange={(e) => set("dietary", e.target.checked ? [...(it.dietary ?? []), d] : (it.dietary ?? []).filter((x) => x !== d))} />{d.replace("_", " ")}</label>))}</div>

      <h3 className="mt-4 text-sm font-semibold">Sizes / variants</h3>
      {variants.map((v, i) => (
        <div key={i} className="mt-1 flex gap-2">
          <input className="input" placeholder="Half" value={v.name} onChange={(e) => setVariants(variants.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
          <input className="input w-28" placeholder="₹" value={v.price} onChange={(e) => setVariants(variants.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} />
          <button className="btn-ghost" onClick={() => setVariants(variants.filter((_, j) => j !== i))}>✕</button>
        </div>))}
      <button className="btn-ghost mt-1 text-xs" onClick={() => setVariants([...variants, { name: "", price_paise: 0, price: "", available: true }])}>+ variant</button>

      <h3 className="mt-4 text-sm font-semibold">Add-on groups</h3>
      {groups.map((g, gi) => (
        <div key={gi} className="mt-2 rounded border border-stone-200 p-2">
          <div className="flex gap-2">
            <input className="input" placeholder="Extras" value={g.name} onChange={(e) => setGroups(groups.map((x, j) => j === gi ? { ...x, name: e.target.value } : x))} />
            <input className="input w-20" type="number" min={0} title="min" value={g.min_select} onChange={(e) => setGroups(groups.map((x, j) => j === gi ? { ...x, min_select: Number(e.target.value) } : x))} />
            <input className="input w-20" type="number" min={1} title="max" value={g.max_select} onChange={(e) => setGroups(groups.map((x, j) => j === gi ? { ...x, max_select: Number(e.target.value) } : x))} />
            <button className="btn-ghost" onClick={() => setGroups(groups.filter((_, j) => j !== gi))}>✕</button>
          </div>
          {g.addons.map((a, ai) => (
            <div key={ai} className="mt-1 flex gap-2 pl-4">
              <input className="input" placeholder="Extra cheese" value={a.name} onChange={(e) => setGroups(groups.map((x, j) => j === gi ? { ...x, addons: x.addons.map((y, k) => k === ai ? { ...y, name: e.target.value } : y) } : x))} />
              <input className="input w-24" placeholder="₹" value={a.price} onChange={(e) => setGroups(groups.map((x, j) => j === gi ? { ...x, addons: x.addons.map((y, k) => k === ai ? { ...y, price: e.target.value } : y) } : x))} />
              <button className="btn-ghost" onClick={() => setGroups(groups.map((x, j) => j === gi ? { ...x, addons: x.addons.filter((_, k) => k !== ai) } : x))}>✕</button>
            </div>))}
          <button className="btn-ghost mt-1 ml-4 text-xs" onClick={() => setGroups(groups.map((x, j) => j === gi ? { ...x, addons: [...x.addons, { name: "", price_paise: 0, price: "", available: true }] } : x))}>+ add-on</button>
        </div>))}
      <button className="btn-ghost mt-1 text-xs" onClick={() => setGroups([...groups, { name: "", min_select: 0, max_select: 1, addons: [] }])}>+ group</button>

      <div className="mt-4 flex gap-2"><ErrorText error={act.error} />
        <button className="btn" disabled={act.busy} onClick={save}>Save dish</button>
        {item.id && <button className="btn-danger" onClick={async () => { if (window.confirm("Remove this dish from the menu?") && await act.run(() => api(`/api/menu/items/${item.id}`, { method: "DELETE" }))) onSaved(); }}>Remove</button>}
      </div>
    </Modal>
  );
}
