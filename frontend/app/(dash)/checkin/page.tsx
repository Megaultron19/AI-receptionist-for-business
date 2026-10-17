"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox, Header, useAction } from "@/components/ui";

type Result = { ok: boolean; message: string; ref?: string; name?: string; guests?: number; time?: string; table?: string | null };

export default function CheckInPage() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [camera, setCamera] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const act = useAction();
  const canScan = typeof window !== "undefined" && "BarcodeDetector" in window;

  async function check(value: string) {
    if (!value.trim()) return;
    const r = await act.run(() => api<Result>("/api/checkin", "POST", { code: value }));
    if (r) setResult(r);
    setCode("");
    input.current?.focus();
  }

  useEffect(() => {
    if (!camera) return;
    let stream: MediaStream | undefined;
    let timer: number | undefined;
    const detector = new (window as any).BarcodeDetector({ formats: ["qr_code"] });
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then((s) => {
      stream = s;
      if (!video.current) return;
      video.current.srcObject = s;
      video.current.play();
      timer = window.setInterval(async () => {
        const found = video.current ? await detector.detect(video.current).catch(() => []) : [];
        if (found.length) {
          setCamera(false);
          check(found[0].rawValue);
        }
      }, 400);
    }).catch(() => setCamera(false));
    return () => {
      window.clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [camera]);

  function submit(e: FormEvent) {
    e.preventDefault();
    check(code);
  }

  return (
    <div className="max-w-lg">
      <Header title="Check-in">
        {canScan && <button className="btn-light" onClick={() => setCamera(!camera)}>{camera ? "Stop camera" : "Use camera"}</button>}
      </Header>
      {camera && <video ref={video} className="mb-4 w-full rounded-lg bg-black" muted playsInline />}
      <form onSubmit={submit} className="flex gap-2">
        <input ref={input} className="input" autoFocus value={code} onChange={(e) => setCode(e.target.value)}
          placeholder="Scan the QR code or type it here" />
        <button className="btn" disabled={act.busy}>Check</button>
      </form>
      <div className="mt-4"><ErrorBox text={act.error} /></div>
      {result && (
        <div className={`card mt-4 border-2 ${result.ok ? "border-green-500" : "border-red-400"}`}>
          <div className={`text-lg font-semibold ${result.ok ? "text-green-700" : "text-red-700"}`}>{result.message}</div>
          {result.ref && (
            <div className="mt-2 space-y-1 text-sm">
              <div>{result.name}, {result.guests} guests at {result.time}</div>
              <div>Table: {result.table ?? "not assigned"}</div>
              <div className="text-stone-500">Booking {result.ref}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
