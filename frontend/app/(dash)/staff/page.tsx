"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { ErrorText, Field, Modal, PageHeader, useAction } from "@/components/ui";

type User = { id: number; name: string; email: string; role: string; active: boolean; last_login_at: string | null };
const ROLES: [string, string][] = [["staff", "Staff - check-in, kitchen, mark arrivals"], ["receptionist", "Receptionist - bookings, orders, inbox, handoff"],
  ["manager", "Manager - menu, tables, settings, refunds, reports"], ["owner", "Owner - everything incl. staff & customer data"]];

export default function StaffPage() {
  const { tz, me } = useApp();
  const users = useApi<User[]>("/api/staff");
  const [adding, setAdding] = useState(false);
  const act = useAction();
  async function patch(u: User, body: object) {
    await act.run(() => api(`/api/staff/${u.id}`, { method: "PATCH", body }));
    users.reload();
  }
  return (
    <div>
      <PageHeader title="Staff accounts"><button className="btn" onClick={() => setAdding(true)}>Add staff</button></PageHeader>
      <ErrorText error={users.error || act.error} />
      <div className="card overflow-x-auto p-0">
        <table className="table">
          <thead><tr><th>Name</th><th>Role</th><th>Last login</th><th></th></tr></thead>
          <tbody>{users.data?.map((u) => (
            <tr key={u.id} className={u.active ? "" : "text-stone-400"}>
              <td>{u.name}<div className="text-xs text-stone-500">{u.email}</div></td>
              <td><select className="input" value={u.role} disabled={u.id === me.id} onChange={(e) => patch(u, { role: e.target.value })}>{ROLES.map(([r]) => <option key={r}>{r}</option>)}</select></td>
              <td className="text-xs">{fmtDateTime(u.last_login_at, tz)}</td>
              <td className="whitespace-nowrap text-right">
                <button className="btn-ghost" onClick={() => { const pw = window.prompt(`New password for ${u.name} (10+ characters)`); if (pw) patch(u, { password: pw }); }}>Reset password</button>
                {u.id !== me.id && <button className="btn-ghost ml-1" onClick={() => patch(u, { active: !u.active })}>{u.active ? "Deactivate" : "Reactivate"}</button>}
              </td>
            </tr>))}</tbody>
        </table>
      </div>
      <ul className="mt-3 text-xs text-stone-500">{ROLES.map(([r, d]) => <li key={r}>{d}</li>)}</ul>
      {adding && <AddStaff onClose={() => setAdding(false)} onSaved={() => { setAdding(false); users.reload(); }} />}
    </div>
  );
}

function AddStaff({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: "", email: "", password: "", role: "staff" });
  const act = useAction();
  return (
    <Modal title="Add staff" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email"><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Temporary password (10+ characters)"><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <Field label="Role"><select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map(([r]) => <option key={r}>{r}</option>)}</select></Field>
      </div>
      <div className="mt-4 space-y-2"><ErrorText error={act.error} /><button className="btn" disabled={act.busy} onClick={async () => { if (await act.run(() => api("/api/staff", { method: "POST", body: f }))) onSaved(); }}>Create</button></div>
    </Modal>
  );
}
