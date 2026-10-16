"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox, Field } from "@/components/ui";

export default function Login() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/api/auth/login", "POST", { username, password });
      router.replace("/");
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <h1 className="text-lg font-semibold">Log in</h1>
        <Field label="Username"><input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></Field>
        <Field label="Password"><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></Field>
        <ErrorBox text={error} />
        <button className="btn w-full">Log in</button>
      </form>
    </div>
  );
}
