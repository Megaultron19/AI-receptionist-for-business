"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, Field, Modal, useAction } from "@/components/ui";

type Me = { username: string; role: string; must_change_password: boolean };
const MeContext = createContext<Me>({ username: "", role: "staff", must_change_password: false });
export const useMe = () => useContext(MeContext);

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/inbox/", label: "Inbox" },
  { href: "/reservations/", label: "Reservations" },
  { href: "/orders/", label: "Orders" },
  { href: "/checkin/", label: "Check-in" },
  { href: "/calls/", label: "Calls" },
  { href: "/tables/", label: "Tables" },
  { href: "/menu/", label: "Menu" },
  { href: "/settings/", label: "Settings", owner: true },
];

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [changing, setChanging] = useState(false);
  const inbox = useApi<{ count: number }>(me ? "/api/inbox/count" : null, 30000);

  useEffect(() => {
    api<Me>("/api/auth/me").then(setMe).catch(() => router.replace("/login/"));
  }, [router]);

  if (!me) return <p className="p-8 text-sm text-stone-500">Loading...</p>;
  if (me.must_change_password) {
    return (
      <main className="mx-auto mt-16 max-w-sm p-4">
        <h1 className="mb-1 text-xl font-semibold">Choose your own password</h1>
        <p className="mb-4 text-sm text-stone-500">You logged in with a temporary password. Pick a new one only you know.</p>
        <PasswordForm onDone={setMe} />
      </main>
    );
  }

  return (
    <MeContext.Provider value={me}>
      <nav className="flex flex-wrap items-center gap-1 border-b border-stone-200 bg-white px-4 py-2">
        <span className="mr-4 font-semibold text-orange-700">Receptionist</span>
        {LINKS.filter((l) => !l.owner || me.role === "owner").map((l) => (
          <Link key={l.href} href={l.href}
            className={`rounded px-3 py-1.5 text-sm ${(l.href === "/" ? path === "/" : path.startsWith(l.href)) ? "bg-orange-50 font-medium text-orange-700" : "text-stone-600 hover:bg-stone-100"}`}>
            {l.label}
            {l.href === "/inbox/" && !!inbox.data?.count && <span className="ml-1 rounded-full bg-red-600 px-1.5 text-xs text-white">{inbox.data.count}</span>}
          </Link>
        ))}
        <span className="ml-auto text-sm text-stone-500">{me.username}</span>
        <button className="btn-light" onClick={() => setChanging(true)}>Password</button>
        <button className="btn-light" onClick={async () => { await api("/api/auth/logout", "POST"); router.replace("/login/"); }}>Log out</button>
      </nav>
      <main className="mx-auto max-w-5xl p-4">{children}</main>
      {changing && <Modal title="Change my password" onClose={() => setChanging(false)}><PasswordForm onDone={(m) => { setMe(m); setChanging(false); }} /></Modal>}
    </MeContext.Provider>
  );
}

function PasswordForm({ onDone }: { onDone: (me: Me) => void }) {
  const [f, setF] = useState({ current: "", new: "", again: "" });
  const act = useAction();
  const mismatch = f.again !== "" && f.again !== f.new;
  return (
    <form className="space-y-3" onSubmit={async (e) => {
      e.preventDefault();
      const me = await act.run(() => api<Me>("/api/auth/password", "POST", { current: f.current, new: f.new }));
      if (me) onDone(me);
    }}>
      <Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} /></Field>
      <Field label="New password (at least 8 characters)"><input className="input" type="password" autoComplete="new-password" value={f.new} onChange={(e) => setF({ ...f, new: e.target.value })} /></Field>
      <Field label="New password again"><input className="input" type="password" autoComplete="new-password" value={f.again} onChange={(e) => setF({ ...f, again: e.target.value })} /></Field>
      {mismatch && <p className="text-sm text-red-700">The new passwords do not match</p>}
      <button className="btn w-full" disabled={act.busy || !f.current || f.new.length < 8 || f.new !== f.again}>Save password</button>
      <ErrorBox text={act.error} />
    </form>
  );
}
