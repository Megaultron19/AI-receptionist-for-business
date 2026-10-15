"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime, rupees, toPaise } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useApp } from "@/components/Shell";
import { Badge, Empty, ErrorText, PageHeader, useAction } from "@/components/ui";

type Payment = { ref: string; purpose: string; status: string; amount_paise: number; refunded_paise: number; refundable_paise: number; short_url: string; created_at: string; paid_at: string | null;
  last_failure: string; order_ref: string | null; reservation_ref: string | null; refunds: { ref: string; amount_paise: number; status: string; reason: string }[] };

export default function PaymentsPage() {
  const { tz, can } = useApp();
  const [status, setStatus] = useState("");
  const list = useApi<Payment[]>(`/api/payments${status ? `?status=${status}` : ""}`, 30000);
  const act = useAction();

  async function refund(p: Payment) {
    const amount = window.prompt(`Refund amount in ₹ (max ${rupees(p.refundable_paise)})`, (p.refundable_paise / 100).toString());
    if (!amount) return;
    const reason = window.prompt("Reason", "customer request");
    if (!reason) return;
    await act.run(() => api(`/api/payments/${p.ref}/refund`, { method: "POST", body: { amount_paise: toPaise(amount), reason } }));
    list.reload();
  }

  return (
    <div>
      <PageHeader title="Payments">
        <select className="input w-44" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All</option>{["created", "pending", "paid", "failed", "expired", "cancelled", "refunded", "partially_refunded"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </select>
      </PageHeader>
      <p className="mb-3 text-sm text-stone-500">Statuses come from Razorpay (verified on the server). Never accept screenshots as proof of payment.</p>
      <ErrorText error={list.error || act.error} />
      <div className="card overflow-x-auto p-0">
        <table className="table">
          <thead><tr><th>Payment</th><th>For</th><th>Amount</th><th>Status</th><th>Refunds</th><th></th></tr></thead>
          <tbody>{list.data?.map((p) => (
            <tr key={p.ref}>
              <td>{p.ref}<div className="text-xs text-stone-500">{fmtDateTime(p.created_at, tz)}</div></td>
              <td>{p.purpose === "order" ? `Order ${p.order_ref}` : `Deposit ${p.reservation_ref}`}</td>
              <td>{rupees(p.amount_paise)}</td>
              <td><Badge status={p.status} />{p.last_failure && <div className="text-xs text-red-700">{p.last_failure}</div>}</td>
              <td className="text-xs">{p.refunds.map((r) => <div key={r.ref}>{rupees(r.amount_paise)} {r.status}</div>)}</td>
              <td className="whitespace-nowrap text-right">
                <button className="btn-ghost" onClick={async () => { await act.run(() => api(`/api/payments/${p.ref}/sync`, { method: "POST" })); list.reload(); }}>Check status</button>
                {can("payments.refund") && p.refundable_paise > 0 && <button className="btn-ghost ml-1" onClick={() => refund(p)}>Refund</button>}
              </td>
            </tr>))}</tbody>
        </table>
        {list.data?.length === 0 && <Empty text="No payments." />}
      </div>
    </div>
  );
}
