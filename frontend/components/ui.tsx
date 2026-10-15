"use client";
import { ReactNode, useState } from "react";
import { STATUS_COLORS, label } from "@/lib/format";

export function Badge({ status }: { status: string }) {
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? "bg-stone-100 text-stone-700"}`}>{label(status)}</span>;
}

export function ErrorText({ error }: { error?: string }) {
  return error ? <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null;
}

export function Notice({ text }: { text?: string }) {
  return text ? <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-800">{text}</p> : null;
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-xl font-semibold">{title}</h1>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4" onClick={onClose}>
      <div role="dialog" aria-label={title} className="mt-10 w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button className="text-stone-500 hover:text-stone-900" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label: l, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{l}</span>
      {children}
    </label>
  );
}

/** Run an async action with busy/error state; returns [run, busy, error, setError]. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }
  return { run, busy, error, setError };
}

export function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-sm text-stone-500">{text}</p>;
}
