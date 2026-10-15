"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export type Me = { id: number; name: string; email: string; role: string; permissions: string[] };
type Ctx = { me: Me; tz: string; restaurant: string; can: (p: string) => boolean };
const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside Shell");
  return ctx;
}

const NAV: { href: string; label: string; perm: string }[] = [
  { href: "/", label: "Overview", perm: "alerts.view" },
  { href: "/reservations/", label: "Reservations", perm: "reservations.view" },
  { href: "/tables/", label: "Tables", perm: "tables.view" },
  { href: "/orders/", label: "Orders", perm: "orders.view" },
  { href: "/menu/", label: "Menu", perm: "menu.view" },
  { href: "/checkin/", label: "QR check-in", perm: "checkin" },
  { href: "/inbox/", label: "WhatsApp inbox", perm: "inbox.view" },
  { href: "/handoff/", label: "Handoff & callbacks", perm: "handoff.manage" },
  { href: "/calls/", label: "Calls", perm: "calls.view" },
  { href: "/payments/", label: "Payments", perm: "payments.view" },
  { href: "/settings/", label: "Settings", perm: "settings.manage" },
  { href: "/staff/", label: "Staff", perm: "staff.manage" },
  { href: "/usage/", label: "Usage & health", perm: "usage.view" },
  { href: "/audit/", label: "Audit & reports", perm: "audit.view" },
  { href: "/privacy/", label: "Customer data", perm: "data.manage" },
];

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [settings, setSettings] = useState<{ timezone: string; name: string } | null>(null);
  const [open, setOpen] = useState(false);
  const alerts = useApi<{ unacknowledged: number }>(me ? "/api/alerts?open_only=true" : null, 20000);

  useEffect(() => {
    api<Me>("/api/auth/me")
      .then(async (m) => {
        setMe(m);
        setSettings(await api("/api/settings"));
      })
      .catch(() => router.replace("/login/"));
  }, [router]);

  if (!me || !settings) return <div className="p-8 text-sm text-stone-500">Loading…</div>;
  const can = (p: string) => me.permissions.includes(p);
  const items = NAV.filter((n) => can(n.perm));

  return (
    <AppContext.Provider value={{ me, tz: settings.timezone, restaurant: settings.name, can }}>
      <div className="min-h-screen md:flex">
        <aside className={`${open ? "block" : "hidden"} border-r border-stone-200 bg-white md:block md:w-56 md:shrink-0`}>
          <div className="px-4 py-4">
            <div className="text-sm font-semibold text-brand">{settings.name}</div>
            <div className="text-xs text-stone-500">AI receptionist</div>
          </div>
          <nav className="flex flex-col pb-4">
            {items.map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href.replace(/\/$/, ""));
              return (
                <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
                  className={`px-4 py-2 text-sm ${active ? "bg-orange-50 font-medium text-brand" : "text-stone-700 hover:bg-stone-50"}`}>
                  {n.label}
                  {n.href === "/" && (alerts.data?.unacknowledged ?? 0) > 0 && (
                    <span className="ml-2 rounded-full bg-red-600 px-1.5 text-xs text-white">{alerts.data!.unacknowledged}</span>
                  )}
                </Link>
              );
            })}
          </nav>
        </aside>
        <div className="flex-1">
          <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-2">
            <button className="btn-ghost md:hidden" onClick={() => setOpen(!open)} aria-label="Menu">☰</button>
            <div className="text-sm text-stone-500">{me.name} · <span className="capitalize">{me.role}</span></div>
            <button className="btn-ghost" onClick={async () => { await api("/api/auth/logout", { method: "POST" }); router.replace("/login/"); }}>
              Log out
            </button>
          </header>
          <main className="mx-auto max-w-6xl p-4">{children}</main>
        </div>
      </div>
    </AppContext.Provider>
  );
}
