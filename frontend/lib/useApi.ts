"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useApi<T>(path: string | null, refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }, [path]);

  useEffect(() => {
    reload();
    if (!refreshMs) return;
    const timer = setInterval(reload, refreshMs);
    return () => clearInterval(timer);
  }, [reload, refreshMs]);

  return { data, error, reload };
}
