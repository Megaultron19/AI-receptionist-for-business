"use client";
import { useState } from "react";
import { fmtDateTime, rupees, todayIn } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { ErrorText, PageHeader } from "@/components/ui";

export default function AuditPage() {
  const { tz, can } = useApp();
  const [start, setStart] = useState(todayIn(tz, -6));
  const [end, setEnd] = useState(todayIn(tz));
  const [q, setQ] = useState("");
  const report = useApi<any>(can("reports.view") ? `/api/reports/summary?start=${start}&end=${end}` : null);
  const log = useApi<any[]>(`/api/audit?limit=300${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  const kv = (o: Record<string, number>) => Object.entries(o).map(([k, v]) => `${k.replace("_", " ")}: ${v}`).join(" · ") || "none";
  return (
    <div className="space-y-5">
      <PageHeader title="Reports & audit log">
        <input type="date" className="input w-40" value={start} onChange={(e) => setStart(e.target.value)} aria-label="From" />
        <input type="date" className="input w-40" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="To" />
      </PageHeader>
      <ErrorText error={report.error || log.error} />
      {report.data && (
        <section className="card grid gap-2 text-sm md:grid-cols-2">
          <div><b>Reservations</b>: {kv(report.data.reservations_by_status)}</div>
          <div><b>By channel</b>: {kv(report.data.reservations_by_source)}</div>
          <div><b>Guests seated</b>: {report.data.covers} · <b>No-shows</b>: {report.data.no_shows}</div>
          <div><b>Orders</b>: {kv(report.data.orders_by_status)}</div>
          <div><b>Order sales</b>: {rupees(report.data.order_sales_paise)}</div>
          <div><b>Payments received</b>: {rupees(report.data.payments_received_paise)} · <b>Refunded</b>: {rupees(report.data.refunded_paise)}</div>
        </section>
      )}
      <section className="card overflow-x-auto p-0">
        <div className="p-3"><input className="input w-72" placeholder="Filter by action or reference" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <table className="table">
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Details</th></tr></thead>
          <tbody>{log.data?.map((a) => (
            <tr key={a.id}><td className="whitespace-nowrap text-xs">{fmtDateTime(a.created_at, tz)}</td><td className="text-xs">{a.actor_type}{a.actor_id ? ` #${a.actor_id}` : ""}</td>
              <td>{a.action}</td><td className="text-xs">{a.entity} {a.entity_id}</td><td className="max-w-md break-all font-mono text-[11px] text-stone-600">{JSON.stringify(a.data)}</td></tr>))}</tbody>
        </table>
      </section>
    </div>
  );
}
