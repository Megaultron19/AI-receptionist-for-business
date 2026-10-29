"use client";
import { useState } from "react";
import { api, time, today } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useMe } from "@/components/Shell";
import { ErrorBox, Field, Header, Modal, useAction } from "@/components/ui";

type Table = { id: number; name: string; seats: number; available: boolean };
type Block = { id: number; table_id: number | null; starts_at: string; ends_at: string; reason: string };

export default function TablesPage() {
  const me = useMe();
  const tables = useApi<Table[]>("/api/tables");
  const blocks = useApi<Block[]>("/api/blocks", 30000);
  const [editing, setEditing] = useState<Partial<Table> | null>(null);
  const [blocking, setBlocking] = useState(false);
  const act = useAction();
  const names = Object.fromEntries((tables.data ?? []).map((t) => [t.id, t.name]));

  const d = new Date();
  const nowIso = `${today()}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const walkIn = (t: Table) => blocks.data?.find((b) => b.table_id === t.id && b.reason === "Walk-in" && b.starts_at.slice(0, 16) <= nowIso && b.ends_at.slice(0, 16) > nowIso);

  async function seat(t: Table) {
    await act.run(() => api(`/api/tables/${t.id}/walk-in`, "POST"));
    blocks.reload();
  }

  async function free(b: Block) {
    await act.run(() => api(`/api/blocks/${b.id}`, "DELETE"));
    blocks.reload();
  }

  async function toggle(t: Table) {
    await act.run(() => api(`/api/tables/${t.id}/available?available=${!t.available}`, "POST"));
    tables.reload();
  }

  return (
    <div className="space-y-6">
      <div>
        <Header title="Tables">
          {me.role === "owner" && <button className="btn" onClick={() => setEditing({ seats: 2, available: true })}>Add table</button>}
        </Header>
        <ErrorBox text={tables.error || act.error} />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {tables.data?.map((t) => (
            <div key={t.id} className={`card ${t.available ? "" : "opacity-60"}`}>
              <div className="text-lg font-semibold">{t.name}</div>
              <div className="text-sm text-stone-500">{t.seats} seats</div>
              {walkIn(t) && <div className="mt-1 text-sm font-medium text-orange-700">Walk-in until {time(walkIn(t)!.ends_at)}</div>}
              <div className="mt-3 flex flex-wrap gap-1">
                {t.available && (walkIn(t)
                  ? <button className="btn" onClick={() => free(walkIn(t)!)}>Table is free again</button>
                  : <button className="btn" onClick={() => seat(t)}>Seat walk-in</button>)}
                <button className="btn-light" onClick={() => toggle(t)}>{t.available ? "Mark unavailable" : "Mark available"}</button>
                {me.role === "owner" && <button className="btn-light" onClick={() => setEditing(t)}>Edit</button>}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <Header title="Blocked times"><button className="btn-light" onClick={() => setBlocking(true)}>Block a time</button></Header>
        <ErrorBox text={blocks.error} />
        <div className="card p-0">
          <table className="table-list">
            <thead><tr><th>From</th><th>To</th><th>Table</th><th>Reason</th><th></th></tr></thead>
            <tbody>
              {blocks.data?.map((b) => (
                <tr key={b.id}>
                  <td>{b.starts_at.replace("T", " ").slice(0, 16)}</td>
                  <td>{b.ends_at.replace("T", " ").slice(0, 16)}</td>
                  <td>{b.table_id ? names[b.table_id] : "All tables"}</td>
                  <td>{b.reason}</td>
                  <td className="text-right"><button className="btn-light" onClick={async () => { await act.run(() => api(`/api/blocks/${b.id}`, "DELETE")); blocks.reload(); }}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {blocks.data?.length === 0 && <p className="p-6 text-center text-sm text-stone-500">Nothing blocked.</p>}
        </div>
      </div>
      {editing && <TableForm table={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); tables.reload(); }} />}
      {blocking && <BlockForm tables={tables.data ?? []} onClose={() => setBlocking(false)} onSaved={() => { setBlocking(false); blocks.reload(); }} />}
    </div>
  );
}

function TableForm({ table, onClose, onSaved }: { table: Partial<Table>; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(table.name ?? "");
  const [seats, setSeats] = useState(table.seats ?? 2);
  const act = useAction();
  const body = { name, seats, available: table.available ?? true };
  return (
    <Modal title={table.id ? `Edit ${table.name}` : "Add table"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="T1" /></Field>
        <Field label="Seats"><input className="input" type="number" min={1} value={seats} onChange={(e) => setSeats(Number(e.target.value))} /></Field>
      </div>
      <div className="mt-4 flex gap-2">
        <button className="btn" disabled={act.busy || !name} onClick={async () => {
          if (await act.run(() => table.id ? api(`/api/tables/${table.id}`, "PUT", body) : api("/api/tables", "POST", body))) onSaved();
        }}>Save</button>
        {table.id && <button className="btn-light" onClick={async () => {
          if (window.confirm(`Delete table ${table.name}?`) && await act.run(() => api(`/api/tables/${table.id}`, "DELETE"))) onSaved();
        }}>Delete</button>}
      </div>
      <div className="mt-2"><ErrorBox text={act.error} /></div>
    </Modal>
  );
}

function BlockForm({ tables, onClose, onSaved }: { tables: Table[]; onClose: () => void; onSaved: () => void }) {
  const [tableId, setTableId] = useState("");
  const [from, setFrom] = useState(`${today()}T18:00`);
  const [to, setTo] = useState(`${today()}T22:00`);
  const [reason, setReason] = useState("");
  const act = useAction();
  return (
    <Modal title="Block a time" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Table">
          <select className="input" value={tableId} onChange={(e) => setTableId(e.target.value)}>
            <option value="">All tables</option>
            {tables.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </Field>
        <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Private party" /></Field>
        <Field label="From"><input className="input" type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="To"><input className="input" type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div>
      <div className="mt-4 space-y-2">
        <ErrorBox text={act.error} />
        <button className="btn" disabled={act.busy} onClick={async () => {
          if (await act.run(() => api("/api/blocks", "POST", { table_id: tableId ? Number(tableId) : null, starts_at: from, ends_at: to, reason }))) onSaved();
        }}>Block</button>
      </div>
    </Modal>
  );
}
