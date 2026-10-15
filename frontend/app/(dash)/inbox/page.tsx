"use client";
import { useState } from "react";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { Badge, Empty, ErrorText, PageHeader } from "@/components/ui";
import { Convo, Thread } from "@/components/Thread";

export default function InboxPage() {
  const { tz, can } = useApp();
  const [mode, setMode] = useState("");
  const list = useApi<Convo[]>(`/api/conversations?channel=whatsapp${mode ? `&mode=${mode}` : ""}`, 10000);
  const [sel, setSel] = useState<number | null>(null);
  return (
    <div>
      <PageHeader title="WhatsApp inbox">
        <select className="input w-44" value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Filter">
          <option value="">All conversations</option><option value="human">Needs staff</option><option value="ai">Handled by AI</option>
        </select>
      </PageHeader>
      <ErrorText error={list.error} />
      <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
        <div className="card max-h-[70vh] divide-y divide-stone-100 overflow-y-auto p-0">
          {list.data?.map((c) => (
            <button key={c.id} onClick={() => setSel(c.id)} className={`block w-full p-3 text-left text-sm ${sel === c.id ? "bg-orange-50" : "hover:bg-stone-50"}`}>
              <div className="flex justify-between"><b className={c.unread ? "" : "font-medium"}>{c.customer.name || c.customer.phone}</b>{c.mode === "human" && <Badge status="open" />}</div>
              <div className="truncate text-xs text-stone-500">{c.last_message}</div>
              <div className="text-xs text-stone-400">{fmtDateTime(c.last_message_at, tz)}</div>
            </button>
          ))}
          {list.data?.length === 0 && <Empty text="No conversations yet." />}
        </div>
        {sel ? <Thread id={sel} canReply={can("inbox.reply")} canHandoff={can("handoff.manage")} onChange={list.reload} /> : <div className="card"><Empty text="Select a conversation." /></div>}
      </div>
    </div>
  );
}

