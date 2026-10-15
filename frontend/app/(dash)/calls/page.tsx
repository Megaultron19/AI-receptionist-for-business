"use client";
import { useState } from "react";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { Empty, ErrorText, PageHeader } from "@/components/ui";
import { Thread } from "@/components/Thread";

type Call = { id: number; provider: string; from_number: string; started_at: string; duration_seconds: number; language: string; turns: number; outcome: string; error: string; conversation_id: number | null };

export default function CallsPage() {
  const { tz } = useApp();
  const [days, setDays] = useState(7);
  const calls = useApi<Call[]>(`/api/calls?days=${days}`, 30000);
  const [sel, setSel] = useState<number | null>(null);
  return (
    <div>
      <PageHeader title="Calls"><select className="input w-36" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">
        {[1, 7, 30, 90].map((d) => <option key={d} value={d}>Last {d} day{d > 1 ? "s" : ""}</option>)}</select></PageHeader>
      <ErrorText error={calls.error} />
      <div className="card overflow-x-auto p-0">
        <table className="table">
          <thead><tr><th>When</th><th>Caller</th><th>Duration</th><th>Lang</th><th>Turns</th><th>Outcome</th><th></th></tr></thead>
          <tbody>{calls.data?.map((c) => (
            <tr key={c.id}><td>{fmtDateTime(c.started_at, tz)}</td><td>{c.from_number}</td><td>{Math.floor(c.duration_seconds / 60)}:{String(c.duration_seconds % 60).padStart(2, "0")}</td>
              <td>{c.language}</td><td>{c.turns}</td><td>{c.outcome.replace("_", " ")}{c.error && <div className="text-xs text-red-700">{c.error}</div>}</td>
              <td>{c.conversation_id && <button className="btn-ghost" onClick={() => setSel(c.conversation_id)}>Transcript</button>}</td></tr>))}</tbody>
        </table>
        {calls.data?.length === 0 && <Empty text="No calls in this period." />}
      </div>
      {sel && <div className="mt-4"><Thread id={sel} canReply={false} canHandoff={false} onChange={() => {}} /></div>}
    </div>
  );
}
