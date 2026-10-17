"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Me = { username: string; role: string };
const MeContext = createContext<Me>({ username: "", role: "staff" });
export const useMe = () => useContext(MeContext);

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/reservations/", label: "Reservations" },
  { href: "/tables/", label: "Tables" },
  { href: "/menu/", label: "Menu" },
  { href: "/settings/", label: "Settings", owner: true },
];

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/api/auth/me").then(setMe).catch(() => router.replace("/login/"));
  }, [router]);

  if (!me) return <p className="p-8 text-sm text-stone-500">Loading...</p>;

  return (
    <MeContext.Provider value={me}>
      <nav className="flex flex-wrap items-center gap-1 border-b border-stone-200 bg-white px-4 py-2">
        <span className="mr-4 font-semibold text-orange-700">Receptionist</span>
        {LINKS.filter((l) => !l.owner || me.role === "owner").map((l) => (
          <Link key={l.href} href={l.href}
            className={`rounded px-3 py-1.5 text-sm ${(l.href === "/" ? path === "/" : path.startsWith(l.href)) ? "bg-orange-50 font-medium text-orange-700" : "text-stone-600 hover:bg-stone-100"}`}>
            {l.label}
          </Link>
        ))}
        <span className="ml-auto text-sm text-stone-500">{me.username}</span>
        <button className="btn-light" onClick={async () => { await api("/api/auth/logout", "POST"); router.replace("/login/"); }}>Log out</button>
      </nav>
      <main className="mx-auto max-w-5xl p-4">{children}</main>
    </MeContext.Provider>
  );
}
