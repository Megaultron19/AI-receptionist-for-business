"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** GET `path` (null = skip), optionally polling. Returns data, error and a reload function. */
export function useApi<T = any>(path: string | null, pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const current = useRef(path);
  current.current = path;

  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      const d = await api<T>(path);
      if (current.current === path) {
        setData(d);
        setError("");
      }
    } catch (e: any) {
      if (current.current === path) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    reload();
    if (!pollMs) return;
    const t = setInterval(reload, pollMs);
    return () => clearInterval(t);
  }, [reload, pollMs]);

  return { data, error, loading, reload, setData };
}
