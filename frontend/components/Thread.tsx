"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { ErrorText, useAction } from "@/components/ui";

export type Convo = { id: number; mode: string; handoff_reason: string; last_message_at: string; unread: boolean; can_reply: boolean; last_message: string;
  customer: { name: string; phone: string; whatsapp_opt_in: boolean } };
export type Msg = { id: number; direction: string; sender: string; body: string; media: string; status: string; error: string; template: string; created_at: string };

export function Thread({ id, canReply, canHandoff, onChange }: { id: number; canReply: boolean; canHandoff: boolean; onChange: () => void }) {
  const { tz } = useApp();
  const t = useApi<Convo & { messages: Msg[] }>(`/api/conversations/${id}`, 8000);
  const [text, setText] = useState("");
  const act = useAction();
  if (!t.data) return <div className="card"><ErrorText error={t.error} /></div>;
  const c = t.data;
  return (
    <div className="card flex max-h-[75vh] flex-col">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-stone-100 pb-2">
        <div><b>{c.customer.name || "Customer"}</b> <span className="text-sm text-stone-500">{c.customer.phone}</span>
          <div className="text-xs text-stone-500">{c.mode === "human" ? `Staff handling${c.handoff_reason ? ` — ${c.handoff_reason}` : ""}` : "AI replying"} · WhatsApp consent: {c.customer.whatsapp_opt_in ? "yes" : "no"}</div></div>
        {canHandoff && (c.mode === "ai"
          ? <button className="btn-ghost" onClick={async () => { await act.run(() => api(`/api/conversations/${id}/handoff`, { method: "POST", body: { reason: "taken over by staff" } })); t.reload(); onChange(); }}>Take over</button>
          : <button className="btn-ghost" onClick={async () => { await act.run(() => api(`/api/conversations/${id}/release`, { method: "POST" })); t.reload(); onChange(); }}>Hand back to AI</button>)}
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto">
        {c.messages.map((m) => (
          <div key={m.id} className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${m.direction === "in" ? "bg-stone-100" : m.sender === "staff" ? "ml-auto bg-sky-100" : "ml-auto bg-orange-50"}`}>
            {m.media && <i>[{m.media}] </i>}{m.body}
            <div className="mt-1 text-[10px] text-stone-500">{m.sender}{m.template && ` · template ${m.template}`} · {fmtDateTime(m.created_at, tz)}{m.direction === "out" && ` · ${m.status}`}{m.error && ` · ${m.error}`}</div>
          </div>
        ))}
      </div>
      {canReply && (c.can_reply ? (
        <form className="mt-2 flex gap-2" onSubmit={async (e) => { e.preventDefault(); if (await act.run(() => api(`/api/conversations/${id}/reply`, { method: "POST", body: { body: text } }))) { setText(""); t.reload(); onChange(); } }}>
          <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Reply as staff (AI pauses on this thread)" />
          <button className="btn" disabled={act.busy || !text.trim()}>Send</button>
        </form>
      ) : <p className="mt-2 text-xs text-stone-500">More than 24 hours since the customer's last message — WhatsApp only allows approved templates. Call the customer instead.</p>)}
      <ErrorText error={act.error} />
    </div>
  );
}
