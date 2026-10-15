"use client";
import Link from "next/link";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { Empty, ErrorText, PageHeader } from "@/components/ui";

type Overview = { reservations_today: number; covers_today: number; orders_open: number; orders_waiting_acceptance: number;
  handoffs_open: number; callbacks_open: number; alerts_open: number; ai_enabled: boolean };
type Alert = { id: number; kind: string; severity: string; message: string; created_at: string; ref_type: string | null; ref_id: string | null };

export default function OverviewPage() {
  const { tz } = useApp();
  const o = useApi<Overview>("/api/overview", 20000);
  const alerts = useApi<{ alerts: Alert[] }>("/api/alerts?open_only=true", 20000);
  const stats: [string, number | undefined, string][] = [
    ["Bookings today", o.data?.reservations_today, "/reservations/"],
    ["Guests expected", o.data?.covers_today, "/reservations/"],
    ["Orders waiting acceptance", o.data?.orders_waiting_acceptance, "/orders/"],
    ["Open orders", o.data?.orders_open, "/orders/"],
    ["Conversations needing staff", o.data?.handoffs_open, "/handoff/"],
    ["Callbacks to make", o.data?.callbacks_open, "/handoff/"],
  ];

  async function ack(id: number) {
    await api(`/api/alerts/${id}/ack`, { method: "POST" });
    alerts.reload();
    o.reload();
  }

  return (
    <div>
      <PageHeader title="Overview" />
      <ErrorText error={o.error || alerts.error} />
      {o.data && !o.data.ai_enabled && <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">The AI receptionist is switched off; calls and chats go to staff.</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {stats.map(([name, value, href]) => (
          <Link key={name} href={href} className="card hover:border-brand">
            <div className="text-2xl font-semibold">{value ?? "–"}</div>
            <div className="text-sm text-stone-500">{name}</div>
          </Link>
        ))}
      </div>
      <h2 className="mb-2 mt-6 text-lg font-semibold">Alerts</h2>
      <div className="card divide-y divide-stone-100 p-0">
        {alerts.data?.alerts.length === 0 && <Empty text="No open alerts." />}
        {alerts.data?.alerts.map((a) => (
          <div key={a.id} className="flex items-start justify-between gap-3 p-3">
            <div>
              <span className={`mr-2 inline-block h-2 w-2 rounded-full ${a.severity === "error" ? "bg-red-600" : a.severity === "warning" ? "bg-amber-500" : "bg-sky-500"}`} />
              <span className="text-sm">{a.message}</span>
              <div className="text-xs text-stone-500">{fmtDateTime(a.created_at, tz)} · {a.kind.replaceAll("_", " ")}</div>
            </div>
            <button className="btn-ghost shrink-0" onClick={() => ack(a.id)}>Acknowledge</button>
          </div>
        ))}
      </div>
    </div>
  );
}
