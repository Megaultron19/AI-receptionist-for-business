"use client";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, useAction } from "@/components/ui";
import { useMe } from "@/components/Shell";

type Status = { on: boolean; tunnel: string; public_url: string; ready: Record<string, boolean> };

export function StartCard() {
  const status = useApi<Status>("/api/receptionist", 15000);
  const act = useAction();
  const me = useMe();
  const s = status.data;
  if (!s) return <ErrorBox text={status.error} />;

  async function toggle() {
    await act.run(() => api(`/api/receptionist/${s!.on ? "stop" : "start"}`, "POST"));
    status.reload();
  }

  return (
    <div className="card mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <div className={`text-lg font-semibold ${s.on ? "text-green-700" : ""}`}>{s.on ? "Receptionist is answering" : "Receptionist is off"}</div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {Object.entries(s.ready).map(([name, ok]) => (
            <span key={name} className={ok ? "text-green-700" : "text-stone-400"}>{ok ? "✓" : "✗"} {name}</span>
          ))}
          {s.tunnel === "down" && <span className="text-red-700">Internet tunnel is down, restarting</span>}
        </div>
        <ErrorBox text={act.error} />
      </div>
      <div className="flex gap-2">
        {me.role === "owner" && <button className="btn-light" disabled={act.busy} title="Use after changing keys in backend/.env"
          onClick={async () => { await act.run(() => api("/api/receptionist/reload", "POST")); status.reload(); }}>Reload keys</button>}
        <button className={s.on ? "btn-light" : "btn px-6 py-3 text-base"} disabled={act.busy} onClick={toggle}>{s.on ? "Stop" : "Start"}</button>
      </div>
    </div>
  );
}
