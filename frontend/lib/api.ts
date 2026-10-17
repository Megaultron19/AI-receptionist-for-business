export class ApiError extends Error {
  constructor(message: string, public status: number, public alternatives: string[] = []) {
    super(message);
  }
}

export async function api<T = any>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Requested-With": "dashboard" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (res.status === 401 && !path.startsWith("/api/auth/login")) window.location.href = "/login/";
  if (!res.ok) {
    const detail = data?.detail;
    if (typeof detail === "object" && detail?.message) throw new ApiError(detail.message, res.status, detail.alternatives ?? []);
    if (Array.isArray(detail)) throw new ApiError(detail.map((d: any) => d.msg).join(", "), res.status);
    throw new ApiError(detail ?? res.statusText, res.status);
  }
  return data as T;
}

export function today(offset = 0): string {
  const d = new Date(Date.now() + offset * 86400000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function time(iso: string): string {
  return iso.slice(11, 16);
}
