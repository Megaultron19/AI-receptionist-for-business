"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtTime, hoursInDay, todayIn } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { ErrorText, Field, Modal, PageHeader, useAction } from "@/components/ui";

type Item = { type: "reservation" | "block"; from: string; to: string; ref?: string; status?: string; party?: number; name?: string; block_id?: number; reason?: string };
type Row = { id: number; code: string; name: string; area: string; capacity: number; items: Item[] };
type Table = { id: number; code: string; name: string; area: string; capacity: number; min_capacity: number; active: boolean; sort: number };
type Combo = { id: number; name: string; capacity: number; min_capacity: number; active: boolean; table_ids: number[]; tables: string[] };

const START_H = 10, END_H = 26; // 10:00 to 02:00 next day

export default function TablesPage() {
  const { tz, can } = useApp();
  const [day, setDay] = useState(todayIn(tz));
  const timeline = useApi<Row[]>(`/api/tables/timeline?day=${day}`, 30000);
  const all = useApi<{ tables: Table[]; combinations: Combo[] }>("/api/tables");
  const [blocking, setBlocking] = useState(false);
  const [editTable, setEditTable] = useState<Partial<Table> | null>(null);
  const [editCombo, setEditCombo] = useState<Partial<Combo> | null>(null);
  const act = useAction();
  const pct = (iso: string) => Math.max(0, Math.min(100, ((hoursInDay(iso, day, tz) - START_H) / (END_H - START_H)) * 100));

  async function unblock(id: number) {
    await act.run(() => api(`/api/tables/blocks/${id}`, { method: "DELETE" }));
    timeline.reload();
  }

  return (
    <div>
      <PageHeader title="Tables">
        <input type="date" className="input w-40" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" />
        {can("tables.block") && <button className="btn" onClick={() => setBlocking(true)}>Block tables</button>}
      </PageHeader>
      <ErrorText error={timeline.error || act.error} />
      <div className="card overflow-x-auto">
        <div className="min-w-[720px]">
          <div className="relative ml-24 h-5 text-xs text-stone-400">
            {Array.from({ length: END_H - START_H + 1 }, (_, i) => (
              <span key={i} className="absolute -translate-x-1/2" style={{ left: `${(i / (END_H - START_H)) * 100}%` }}>{(START_H + i) % 24}:00</span>
            ))}
          </div>
          {timeline.data?.map((t) => (
            <div key={t.id} className="flex items-center border-t border-stone-100 py-1">
              <div className="w-24 shrink-0 text-sm"><b>{t.code}</b> <span className="text-xs text-stone-500">({t.capacity}) {t.area}</span></div>
              <div className="relative h-9 flex-1 rounded bg-stone-50">
                {t.items.map((it, i) => (
                  <div key={i} title={it.type === "block" ? `Blocked: ${it.reason}` : `${it.ref} ${it.name} · ${it.party} guests · ${it.status}`}
                    className={`absolute top-1 flex h-7 items-center overflow-hidden rounded px-1 text-xs ${it.type === "block" ? "bg-stone-400 text-white" : it.status === "held" ? "bg-amber-300" : it.status === "seated" || it.status === "arrived" ? "bg-indigo-300" : "bg-green-300"}`}
                    style={{ left: `${pct(it.from)}%`, width: `${Math.max(pct(it.to) - pct(it.from), 1)}%` }}>
                    {it.type === "block" ? (
                      <>Blocked {can("tables.block") && <button className="ml-1 underline" onClick={() => unblock(it.block_id!)}>unblock</button>}</>
                    ) : (<>{fmtTime(it.from, tz)} {it.name || it.ref} ({it.party})</>)}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-stone-500">Green confirmed · amber held · indigo arrived/seated · grey blocked. Bars include the cleaning buffer.</p>
      </div>

      {can("tables.manage") && (
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <div className="card">
            <div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Tables</h2>
              <button className="btn-ghost" onClick={() => setEditTable({ capacity: 2, min_capacity: 1, active: true, sort: 0 })}>Add table</button></div>
            <table className="table">
              <thead><tr><th>Code</th><th>Seats</th><th>Area</th><th></th></tr></thead>
              <tbody>{all.data?.tables.map((t) => (
                <tr key={t.id} className={t.active ? "" : "text-stone-400"}><td>{t.code} {t.name}</td><td>{t.min_capacity}–{t.capacity}</td><td>{t.area}</td>
                  <td className="text-right"><button className="btn-ghost" onClick={() => setEditTable(t)}>Edit</button></td></tr>))}</tbody>
            </table>
          </div>
          <div className="card">
            <div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Combinations</h2>
              <button className="btn-ghost" onClick={() => setEditCombo({ table_ids: [], active: true, min_capacity: 1 })}>Add combination</button></div>
            <table className="table">
              <thead><tr><th>Name</th><th>Tables</th><th>Seats</th><th></th></tr></thead>
              <tbody>{all.data?.combinations.map((c) => (
                <tr key={c.id}><td>{c.name}</td><td>{c.tables.join(" + ")}</td><td>{c.min_capacity}–{c.capacity}</td>
                  <td className="text-right"><button className="btn-ghost" onClick={() => setEditCombo(c)}>Edit</button></td></tr>))}</tbody>
            </table>
          </div>
        </div>
      )}
      {blocking && <BlockForm day={day} tables={all.data?.tables ?? []} onClose={() => setBlocking(false)} onSaved={() => { setBlocking(false); timeline.reload(); }} />}
      {editTable && <TableForm table={editTable} onClose={() => setEditTable(null)} onSaved={() => { setEditTable(null); all.reload(); timeline.reload(); }} />}
      {editCombo && <ComboForm combo={editCombo} tables={all.data?.tables ?? []} onClose={() => setEditCombo(null)} onSaved={() => { setEditCombo(null); all.reload(); }} />}
    </div>
  );
}

function BlockForm({ day, tables, onClose, onSaved }: { day: string; tables: Table[]; onClose: () => void; onSaved: () => void }) {
  const [ids, setIds] = useState<number[]>([]);
  const [from, setFrom] = useState(`${day}T18:00`);
  const [to, setTo] = useState(`${day}T23:00`);
  const [reason, setReason] = useState("");
  const act = useAction();
  return (
    <Modal title="Block tables" onClose={onClose}>
      <div className="flex flex-wrap gap-1">{tables.filter((t) => t.active).map((t) => (
        <label key={t.id} className="flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs">
          <input type="checkbox" checked={ids.includes(t.id)} onChange={(e) => setIds(e.target.checked ? [...ids, t.id] : ids.filter((x) => x !== t.id))} />{t.code}</label>))}</div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Field label="From"><input className="input" type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="To"><input className="input" type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div>
      <Field label="Reason" className="mt-3"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Private event, repair…" /></Field>
      <div className="mt-4 space-y-2"><ErrorText error={act.error} />
        <button className="btn" disabled={act.busy || !ids.length} onClick={async () => {
          if (await act.run(() => api("/api/tables/blocks", { method: "POST", body: { table_ids: ids, starts_at: from, ends_at: to, reason } }))) onSaved();
        }}>Block</button></div>
    </Modal>
  );
}

function TableForm({ table, onClose, onSaved }: { table: Partial<Table>; onClose: () => void; onSaved: () => void }) {
  const [t, setT] = useState<Partial<Table>>(table);
  const act = useAction();
  return (
    <Modal title={table.id ? `Edit ${table.code}` : "Add table"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Code"><input className="input" value={t.code ?? ""} onChange={(e) => setT({ ...t, code: e.target.value })} /></Field>
        <Field label="Name"><input className="input" value={t.name ?? ""} onChange={(e) => setT({ ...t, name: e.target.value })} /></Field>
        <Field label="Area"><input className="input" value={t.area ?? ""} onChange={(e) => setT({ ...t, area: e.target.value })} /></Field>
        <Field label="Sort order"><input className="input" type="number" value={t.sort ?? 0} onChange={(e) => setT({ ...t, sort: Number(e.target.value) })} /></Field>
        <Field label="Max guests"><input className="input" type="number" min={1} value={t.capacity ?? 2} onChange={(e) => setT({ ...t, capacity: Number(e.target.value) })} /></Field>
        <Field label="Min guests"><input className="input" type="number" min={1} value={t.min_capacity ?? 1} onChange={(e) => setT({ ...t, min_capacity: Number(e.target.value) })} /></Field>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={t.active ?? true} onChange={(e) => setT({ ...t, active: e.target.checked })} /> Active (bookable)</label>
      <div className="mt-4 space-y-2"><ErrorText error={act.error} />
        <button className="btn" disabled={act.busy} onClick={async () => {
          const body = { code: t.code, name: t.name ?? "", area: t.area ?? "", capacity: t.capacity, min_capacity: t.min_capacity, active: t.active ?? true, sort: t.sort ?? 0 };
          if (await act.run(() => api(table.id ? `/api/tables/${table.id}` : "/api/tables", { method: table.id ? "PUT" : "POST", body }))) onSaved();
        }}>Save</button></div>
    </Modal>
  );
}

function ComboForm({ combo, tables, onClose, onSaved }: { combo: Partial<Combo>; tables: Table[]; onClose: () => void; onSaved: () => void }) {
  const [c, setC] = useState<Partial<Combo>>(combo);
  const act = useAction();
  const ids = c.table_ids ?? [];
  return (
    <Modal title={combo.id ? `Edit ${combo.name}` : "Add combination"} onClose={onClose}>
      <Field label="Name"><input className="input" value={c.name ?? ""} onChange={(e) => setC({ ...c, name: e.target.value })} /></Field>
      <div className="mt-3 flex flex-wrap gap-1">{tables.map((t) => (
        <label key={t.id} className="flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs">
          <input type="checkbox" checked={ids.includes(t.id)} onChange={(e) => setC({ ...c, table_ids: e.target.checked ? [...ids, t.id] : ids.filter((x) => x !== t.id) })} />{t.code} ({t.capacity})</label>))}</div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Field label="Max guests (blank = sum of tables)"><input className="input" type="number" value={c.capacity ?? ""} onChange={(e) => setC({ ...c, capacity: e.target.value ? Number(e.target.value) : undefined })} /></Field>
        <Field label="Min guests"><input className="input" type="number" min={1} value={c.min_capacity ?? 1} onChange={(e) => setC({ ...c, min_capacity: Number(e.target.value) })} /></Field>
      </div>
      <div className="mt-4 flex gap-2"><ErrorText error={act.error} />
        <button className="btn" disabled={act.busy || ids.length < 2} onClick={async () => {
          const body = { name: c.name, table_ids: ids, capacity: c.capacity ?? null, min_capacity: c.min_capacity ?? 1, active: c.active ?? true };
          if (await act.run(() => api(combo.id ? `/api/tables/combinations/${combo.id}` : "/api/tables/combinations", { method: combo.id ? "PUT" : "POST", body }))) onSaved();
        }}>Save</button>
        {combo.id && <button className="btn-danger" onClick={async () => { if (await act.run(() => api(`/api/tables/combinations/${combo.id}`, { method: "DELETE" }))) onSaved(); }}>Delete</button>}
      </div>
    </Modal>
  );
}
