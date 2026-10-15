"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime, rupees } from "@/lib/format";
import { useApp } from "@/components/Shell";
import { Badge, ErrorText, PageHeader, useAction } from "@/components/ui";

type Result = { result: string; message: string; kind?: string; ref?: string; status?: string; name?: string; party_size?: number; starts_at?: string;
  items?: string[]; total_paise?: number; balance_due_paise?: number; payment_verified?: boolean; scan_count?: number; notes?: string };

const GOOD = new Set(["valid", "checked_in", "handed_over"]);

export default function CheckinPage() {
  const { tz } = useApp();
  const [code, setCode] = useState("");
  const [res, setRes] = useState<Result | null>(null);
  const [camera, setCamera] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const act = useAction();
  const supported = typeof window !== "undefined" && "BarcodeDetector" in window;

  async function lookup(c: string) {
    setCode(c);
    const r = await act.run(() => api<Result>("/api/checkin/lookup", { method: "POST", body: { code: c } }));
    if (r) setRes(r);
  }

  useEffect(() => {
    if (!camera) return;
    let stream: MediaStream | null = null, stop = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        video.current!.srcObject = stream;
        await video.current!.play();
        const detector = new (window as any).BarcodeDetector({ formats: ["qr_code"] });
        while (!stop) {
          const codes = await detector.detect(video.current!);
          if (codes.length) { setCamera(false); lookup(codes[0].rawValue); break; }
          await new Promise((r) => setTimeout(r, 300));
        }
      } catch (e: any) {
        act.setError(`Camera unavailable: ${e.message}. Type or paste the code instead.`);
        setCamera(false);
      }
    })();
    return () => { stop = true; stream?.getTracks().forEach((t) => t.stop()); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera]);

  return (
    <div className="max-w-xl">
      <PageHeader title="QR check-in" />
      <div className="card space-y-3">
        {supported && <button className="btn w-full" onClick={() => { setRes(null); setCamera(!camera); }}>{camera ? "Stop camera" : "Scan with camera"}</button>}
        {camera && <video ref={video} className="w-full rounded" muted playsInline />}
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); lookup(code); }}>
          <input className="input" placeholder="Paste QR link or code" value={code} onChange={(e) => setCode(e.target.value)} />
          <button className="btn" disabled={act.busy || code.length < 10}>Look up</button>
        </form>
        <ErrorText error={act.error} />
      </div>
      {res && (
        <div className={`card mt-4 border-2 ${GOOD.has(res.result) ? "border-green-500" : "border-red-400"}`}>
          <p className="text-lg font-semibold">{res.message}</p>
          {res.ref && <p className="mt-1 text-sm">{res.kind === "reservation" ? "Booking" : "Order"} <b>{res.ref}</b> {res.status && <Badge status={res.status} />}</p>}
          {res.name && <p className="text-sm">{res.name}</p>}
          {res.kind === "reservation" && <p className="text-sm">{res.party_size} guests · {fmtDateTime(res.starts_at, tz)}{res.notes && ` · “${res.notes}”`}</p>}
          {res.items && <ul className="mt-1 text-sm">{res.items.map((i) => <li key={i}>{i}</li>)}</ul>}
          {res.kind === "order" && <p className="text-sm">Total {rupees(res.total_paise)} · {res.payment_verified ? "payment verified" : "payment NOT verified"}{(res.balance_due_paise ?? 0) > 0 && ` · collect ${rupees(res.balance_due_paise)}`}</p>}
          {res.scan_count && res.scan_count > 1 && <p className="text-xs text-stone-500">Scanned {res.scan_count} times</p>}
          {res.result === "valid" && (
            <button className="btn mt-3" disabled={act.busy} onClick={async () => { const r = await act.run(() => api<Result>("/api/checkin/confirm", { method: "POST", body: { code } })); if (r) setRes(r); }}>
              {res.kind === "reservation" ? "Check guest in" : "Hand over order"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
