"use client";
import { useState } from "react";
import { fmtDateTime, rupees } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { ErrorText, PageHeader } from "@/components/ui";

const NAMES: Record<string, string> = {
  voice_call: "Voice calls", voice_seconds: "Voice seconds", whatsapp_in: "WhatsApp messages in", whatsapp_out: "WhatsApp messages out",
  llm_input_tokens: "AI input tokens", llm_output_tokens: "AI output tokens", reservation_created: "Reservations created",
  order_completed: "Orders completed", payment_paid: "Payments received", payment_refunded: "Refunds", webhook_razorpay: "Razorpay webhooks",
};

export default function UsagePage() {
  const { tz, can } = useApp();
  const [days, setDays] = useState(30);
  const usage = useApi<any>(`/api/usage?days=${days}`);
  const health = useApi<any>(can("health.view") ? "/api/health/integrations" : null, 30000);
  return (
    <div className="space-y-5">
      <PageHeader title="Usage & integration health">
        <select className="input w-36" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">{[7, 30, 90, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select>
      </PageHeader>
      <ErrorText error={usage.error || health.error} />
      {health.data && (
        <section className="card">
          <h2 className="mb-2 font-semibold">Integrations</h2>
          <table className="table"><thead><tr><th>Service</th><th>Configured</th><th>Last success</th><th>Last failure</th><th>Status</th></tr></thead>
            <tbody>{Object.entries<any>(health.data.integrations).map(([name, i]) => {
              const bad = !i.configured || i.consecutive_failures > 0;
              return <tr key={name}><td className="capitalize">{name}</td><td>{i.configured ? "yes" : "no"}</td><td className="text-xs">{fmtDateTime(i.last_success_at, tz)}</td>
                <td className="text-xs">{fmtDateTime(i.last_failure_at, tz)}{i.last_error && <div className="text-red-700">{i.last_error}</div>}</td>
                <td><span className={`inline-block h-2 w-2 rounded-full ${bad ? "bg-red-600" : "bg-green-600"}`} /> {i.consecutive_failures > 0 ? `${i.consecutive_failures} failures in a row` : i.configured ? "ok" : "not set up"}</td></tr>;
            })}</tbody></table>
          <p className="mt-2 text-sm">Background worker: <b className={health.data.worker.alive ? "text-green-700" : "text-red-700"}>{health.data.worker.alive ? "running" : "NOT RUNNING"}</b> (last heartbeat {fmtDateTime(health.data.worker.last_heartbeat, tz)}) ·
            jobs {Object.entries(health.data.jobs.by_status).map(([k, v]) => `${k} ${v}`).join(", ") || "none"} · overdue {health.data.jobs.overdue}</p>
          <p className="text-sm">Webhooks (24h): {Object.entries(health.data.webhooks_24h).map(([k, v]) => `${k} ${v}`).join(", ") || "none"}</p>
        </section>
      )}
      {usage.data && (
        <section className="card">
          <h2 className="mb-2 font-semibold">Usage — last {usage.data.days} days</h2>
          <table className="table"><thead><tr><th>Metric</th><th className="text-right">Quantity</th><th className="text-right">Estimated cost</th></tr></thead>
            <tbody>{Object.entries<any>(usage.data.totals).sort().map(([k, t]) => (
              <tr key={k}><td>{NAMES[k] ?? k}</td><td className="text-right">{t.quantity.toLocaleString("en-IN")}</td><td className="text-right">{t.cost_paise ? rupees(t.cost_paise) : "–"}</td></tr>))}</tbody>
            <tfoot><tr><td className="font-semibold">Estimated provider costs</td><td /><td className="text-right font-semibold">{rupees(usage.data.estimated_cost_paise)}</td></tr></tfoot></table>
          <p className="mt-2 text-xs text-stone-500">{usage.data.note}</p>
        </section>
      )}
    </div>
  );
}
