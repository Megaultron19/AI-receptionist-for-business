export class ApiError extends Error {
  constructor(message: string, public status: number, public code: string) {
    super(message);
  }
}

export function csrfToken(cookie: string = typeof document === "undefined" ? "" : document.cookie): string {
  const raw = cookie.split("; ").find((c) => c.startsWith("rr_csrf="));
  return raw ? decodeURIComponent(raw.slice("rr_csrf=".length)) : "";
}

type Options = { method?: string; body?: unknown };

/** Same-origin JSON API call. Mutating requests carry the CSRF double-submit header. */
export async function api<T = any>(path: string, { method = "GET", body }: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  const res = await fetch(path, { method, headers, credentials: "same-origin", body: body === undefined ? undefined : JSON.stringify(body) });
  const data = res.headers.get("content-type")?.includes("application/json") ? await res.json() : null;
  if (res.status === 401 && !path.startsWith("/api/auth/") && typeof window !== "undefined") {
    window.location.href = "/login/";
  }
  if (!res.ok) throw new ApiError(data?.detail ?? res.statusText, res.status, data?.error ?? "error");
  return data as T;
}
