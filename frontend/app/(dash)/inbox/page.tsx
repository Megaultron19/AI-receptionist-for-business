"use client";
import { useState } from "react";
import { api, time } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorBox, Header, useAction } from "@/components/ui";

type Line = { who: string; text: string };
type Chat = { phone: string; name: string; last_message_at: string | null; can_reply: boolean; transcript: Line[] };
type Inbox = { chats: Chat[]; notices: { id: number; text: string; seen: boolean; at: string }[]; problems: { kind: string; detail: string; at: string }[] };

const when = (iso: string) => `${iso.slice(5, 10)} ${time(iso)}`;

export default function InboxPage() {
  const inbox = useApi<Inbox>("/api/inbox", 10000);
  const act = useAction();
  const unseen = inbox.data?.notices.some((n) => !n.seen);

  return (
    <div className="space-y-6">
      <Header title="Inbox" />
      <ErrorBox text={inbox.error || act.error} />
      <section>
        <h2 className="mb-2 font-semibold">Chats waiting for staff</h2>
        {inbox.data?.chats.length === 0 && <p className="card text-sm text-stone-500">Nobody is waiting.</p>}
        <div className="grid gap-3 md:grid-cols-2">
          {inbox.data?.chats.map((c) => <ChatCard key={c.phone} chat={c} onDone={inbox.reload} />)}
        </div>
      </section>
      <section>
        <Header title="Updates">
          {unseen && <button className="btn-light" onClick={async () => { await act.run(() => api("/api/inbox/seen", "POST")); inbox.reload(); }}>Mark all read</button>}
        </Header>
        <div className="card divide-y divide-stone-100 p-0 text-sm">
          {inbox.data?.notices.map((n) => (
            <div key={n.id} className={`flex gap-3 p-3 ${n.seen ? "text-stone-500" : "font-medium"}`}>
              <span className="w-24 shrink-0 text-stone-500">{when(n.at)}</span><span>{n.text}</span>
            </div>
          ))}
          {inbox.data?.notices.length === 0 && <p className="p-3 text-stone-500">No updates yet.</p>}
        </div>
      </section>
      {!!inbox.data?.problems.length && (
        <section>
          <h2 className="mb-2 font-semibold">Problems</h2>
          <div className="card divide-y divide-stone-100 p-0 text-sm">
            {inbox.data.problems.map((p, n) => (
              <div key={n} className="flex gap-3 p-3">
                <span className="w-24 shrink-0 text-stone-500">{when(p.at)}</span>
                <span><b>{p.kind.replaceAll("_", " ")}</b>: {p.detail}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ChatCard({ chat, onDone }: { chat: Chat; onDone: () => void }) {
  const [text, setText] = useState("");
  const act = useAction();
  const post = async (path: string, body: object) => {
    if (await act.run(() => api(path, "POST", body))) { setText(""); onDone(); }
  };
  return (
    <div className="card">
      <div className="mb-2 flex justify-between gap-2">
        <b>{chat.name || chat.phone}</b><span className="text-xs text-stone-500">{chat.phone}</span>
      </div>
      <div className="mb-3 max-h-72 space-y-1 overflow-y-auto text-sm">
        {chat.transcript.map((l, n) => (
          <p key={n} className={l.who === "customer" ? "" : l.who === "staff" ? "text-green-800" : "text-orange-800"}>
            <b>{l.who === "customer" ? "Customer" : l.who === "staff" ? "You" : "Receptionist"}:</b> {l.text}
          </p>
        ))}
      </div>
      {chat.can_reply ? (
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); post("/api/inbox/reply", { phone: chat.phone, text }); }}>
          <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a reply" />
          <button className="btn" disabled={act.busy || !text.trim()}>Send</button>
        </form>
      ) : <p className="text-xs text-stone-500">Last message was over 24 hours ago, so WhatsApp only allows a phone call now.</p>}
      <div className="mt-2 flex items-center justify-between">
        <button className="btn-light" onClick={() => post("/api/inbox/release", { phone: chat.phone })}>Hand back to the AI</button>
      </div>
      <div className="mt-2"><ErrorBox text={act.error} /></div>
    </div>
  );
}
