"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { Empty, ErrorText, Field, Modal, PageHeader, useAction } from "@/components/ui";
import { Thread } from "@/components/Thread";

type Q = { conversations: { id: number; handoff_reason: string; handoff_at: string; customer: { name: string; phone: string } }[];
  callbacks: { id: number; phone: string; name: string; reason: string; source: string; created_at: string }[] };

export default function HandoffPage() {
  const { tz, can } = useApp();
  const q = useApi<Q>("/api/handoff", 10000);
  const [sel, setSel] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const act = useAction();
  return (
    <div>
      <PageHeader title="Handoff queue & callbacks">{can("callbacks.manage") && <button className="btn-ghost" onClick={() => setAdding(true)}>Log callback</button>}</PageHeader>
      <ErrorText error={q.error || act.error} />
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h2 className="mb-2 font-semibold">Conversations needing staff</h2>
          <div className="card divide-y divide-stone-100 p-0">
            {q.data?.conversations.map((c) => (
              <button key={c.id} onClick={() => setSel(c.id)} className="block w-full p-3 text-left text-sm hover:bg-stone-50">
                <b>{c.customer.name || c.customer.phone}</b> <span className="text-stone-500">{c.customer.phone}</span>
                <div className="text-xs">{c.handoff_reason}</div><div className="text-xs text-stone-400">since {fmtDateTime(c.handoff_at, tz)}</div>
              </button>))}
            {q.data?.conversations.length === 0 && <Empty text="Nothing waiting." />}
          </div>
          <h2 className="mb-2 mt-4 font-semibold">Callbacks</h2>
          <div className="card divide-y divide-stone-100 p-0">
            {q.data?.callbacks.map((cb) => (
              <div key={cb.id} className="flex items-start justify-between gap-2 p-3 text-sm">
                <div><b>{cb.name || "Customer"}</b> <a className="text-brand underline" href={`tel:${cb.phone}`}>{cb.phone}</a>
                  <div className="text-xs">{cb.reason}</div><div className="text-xs text-stone-400">{cb.source} · {fmtDateTime(cb.created_at, tz)}</div></div>
                <div className="flex gap-1">
                  <button className="btn-ghost" onClick={async () => { const note = window.prompt("Outcome note", "Called back"); if (note === null) return; await act.run(() => api(`/api/callbacks/${cb.id}/done`, { method: "POST", body: { note } })); q.reload(); }}>Done</button>
                  <button className="btn-ghost" onClick={async () => { await act.run(() => api(`/api/callbacks/${cb.id}/done`, { method: "POST", body: { status: "cancelled" } })); q.reload(); }}>Dismiss</button>
                </div>
              </div>))}
            {q.data?.callbacks.length === 0 && <Empty text="No callbacks to make." />}
          </div>
        </div>
        {sel ? <Thread id={sel} canReply={can("inbox.reply")} canHandoff={can("handoff.manage")} onChange={q.reload} /> : <div className="card"><Empty text="Select a conversation." /></div>}
      </div>
      {adding && <CallbackForm onClose={() => setAdding(false)} onSaved={() => { setAdding(false); q.reload(); }} />}
    </div>
  );
}

function CallbackForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ phone: "", name: "", reason: "" });
  const act = useAction();
  return (
    <Modal title="Log a callback" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Reason" className="col-span-2"><input className="input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
      </div>
      <div className="mt-4 space-y-2"><ErrorText error={act.error} /><button className="btn" disabled={act.busy} onClick={async () => { if (await act.run(() => api("/api/callbacks", { method: "POST", body: f }))) onSaved(); }}>Save</button></div>
    </Modal>
  );
}
