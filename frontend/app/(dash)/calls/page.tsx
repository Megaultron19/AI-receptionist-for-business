"use client";
import { useState } from "react";
import { time } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, Header } from "@/components/ui";

type Call = { id: string; phone: string; started_at: string; ended_at: string | null; outcome: string; transcript: { who: string; text: string }[] };

export default function CallsPage() {
  const calls = useApi<Call[]>("/api/calls", 15000);
  const [open, setOpen] = useState("");

  return (
    <div>
      <Header title="Calls" />
      <ErrorBox text={calls.error} />
      <div className="card divide-y divide-stone-100 p-0">
        {calls.data?.map((c) => (
          <div key={c.id} className="p-3">
            <button className="flex w-full items-center justify-between gap-2 text-left text-sm" onClick={() => setOpen(open === c.id ? "" : c.id)}>
              <span><b>{c.phone || "Hidden number"}</b> <span className="text-stone-500">{c.started_at.slice(0, 10)} {time(c.started_at)}</span></span>
              <span className={c.outcome === "needs callback" ? "font-medium text-red-700" : "text-stone-600"}>{c.outcome}</span>
            </button>
            {open === c.id && (
              <div className="mt-2 space-y-1 text-sm">
                {c.transcript.map((line, n) => (
                  <p key={n} className={line.who === "customer" ? "" : "text-orange-800"}><b>{line.who === "customer" ? "Caller" : "Receptionist"}:</b> {line.text}</p>
                ))}
                {c.transcript.length === 0 && <p className="text-stone-500">Nothing was said.</p>}
              </div>
            )}
          </div>
        ))}
        {calls.data?.length === 0 && <p className="p-4 text-center text-sm text-stone-500">No calls yet.</p>}
      </div>
    </div>
  );
}
