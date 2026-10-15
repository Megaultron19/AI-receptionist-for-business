"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorText, Notice, PageHeader, useAction } from "@/components/ui";

type Customer = { id: number; name: string; phone: string; whatsapp_opt_in: boolean };

export default function PrivacyPage() {
  const [q, setQ] = useState("");
  const list = useApi<Customer[]>(`/api/customers?q=${encodeURIComponent(q)}`);
  const act = useAction();
  const [ok, setOk] = useState("");

  function download(name: string, data: unknown) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    a.download = name;
    a.click();
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Customer data & configuration" />
      <section className="card">
        <h2 className="mb-2 font-semibold">Customer data requests</h2>
        <p className="mb-2 text-sm text-stone-500">Export everything stored about a customer, or erase their personal data. Bookings, orders and payments stay as anonymous records for accounting/GST. Razorpay keeps its own records; handle those in the Razorpay dashboard.</p>
        <input className="input mb-2 w-72" placeholder="Search name or phone" value={q} onChange={(e) => setQ(e.target.value)} />
        <ErrorText error={list.error || act.error} /><Notice text={ok} />
        <table className="table"><tbody>{list.data?.map((c) => (
          <tr key={c.id}><td>{c.name || "-"}</td><td>{c.phone}</td><td>{c.whatsapp_opt_in ? "WhatsApp consent" : ""}</td>
            <td className="whitespace-nowrap text-right">
              <button className="btn-ghost" onClick={async () => { const d = await act.run(() => api(`/api/customers/${c.id}/export`)); if (d) download(`customer-${c.id}.json`, d); }}>Export</button>
              <button className="btn-ghost ml-1 text-red-700" onClick={async () => {
                if (!window.confirm(`Permanently erase personal data for ${c.name || c.phone}? This cannot be undone.`)) return;
                if (await act.run(() => api(`/api/customers/${c.id}/anonymize`, { method: "POST" }))) { setOk("Customer data erased."); list.reload(); }
              }}>Erase</button></td></tr>))}</tbody></table>
      </section>
      <section className="card">
        <h2 className="mb-2 font-semibold">Restaurant configuration</h2>
        <p className="mb-2 text-sm text-stone-500">Settings, tables and menu as a file (no passwords or API keys). Use it to back up your setup or copy it to a new installation.</p>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={async () => { const d = await act.run(() => api("/api/config/export")); if (d) download("restaurant-config.json", d); }}>Export configuration</button>
          <label className="btn-ghost cursor-pointer">Import configuration…<input type="file" accept="application/json" className="hidden" onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            const replace = window.confirm("Replace the current menu with the file's menu? (Cancel = add to it)");
            const out = await act.run(async () => api("/api/config/import", { method: "POST", body: { config: JSON.parse(await file.text()), replace_menu: replace } }));
            if (out) setOk(`Imported ${out.tables} tables and ${out.menu_items} dishes.`);
          }} /></label>
        </div>
      </section>
    </div>
  );
}
