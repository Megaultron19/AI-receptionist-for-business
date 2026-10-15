import { describe, expect, it, vi } from "vitest";
import { hhmm, hoursInDay, label, rupees, toPaise, todayIn } from "../lib/format";
import { api, ApiError, csrfToken } from "../lib/api";

describe("money", () => {
  it("formats paise with Indian grouping", () => {
    expect(rupees(12345650)).toBe("₹1,23,456.50");
    expect(rupees(5000)).toBe("₹50");
    expect(rupees(-2550)).toBe("-₹25.50");
    expect(rupees(null)).toBe("-");
  });
  it("parses rupee input exactly (no float drift)", () => {
    expect(toPaise("18.5")).toBe(1850);
    expect(toPaise("0.07")).toBe(7);
    expect(toPaise("1999.99")).toBe(199999);
    expect(() => toPaise("12.345")).toThrow();
    expect(() => toPaise("abc")).toThrow();
  });
});

describe("time in the restaurant's timezone", () => {
  it("places times on the day timeline, including after midnight", () => {
    expect(hoursInDay("2026-10-20T13:30:00Z", "2026-10-20", "Asia/Kolkata")).toBe(19);
    expect(hoursInDay("2026-10-20T20:00:00Z", "2026-10-20", "Asia/Kolkata")).toBe(25.5);
    expect(hhmm("2026-10-20T13:30:00Z", "Asia/Kolkata")).toBe("19:00");
  });
  it("computes today's date in the restaurant timezone", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-20T20:00:00Z"));
    expect(todayIn("Asia/Kolkata")).toBe("2026-10-21");
    expect(todayIn("UTC")).toBe("2026-10-20");
    vi.useRealTimers();
  });
  it("labels statuses", () => expect(label("no_show")).toBe("No show"));
});

describe("api client", () => {
  it("reads the CSRF cookie", () => {
    expect(csrfToken("a=1; rr_csrf=abc%2Fdef; b=2")).toBe("abc/def");
    expect(csrfToken("a=1")).toBe("");
  });
  it("sends the CSRF header on writes and surfaces server error messages", async () => {
    const calls: RequestInit[] = [];
    vi.stubGlobal("document", { cookie: "rr_csrf=tok123" });
    vi.stubGlobal("fetch", async (_url: string, init: RequestInit) => {
      calls.push(init);
      return new Response(JSON.stringify({ error: "conflict", detail: "No table is free for that time." }), { status: 409, headers: { "content-type": "application/json" } });
    });
    await expect(api("/api/reservations", { method: "POST", body: { party_size: 2 } })).rejects.toThrowError(new ApiError("No table is free for that time.", 409, "conflict"));
    expect((calls[0].headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
    vi.unstubAllGlobals();
  });
});
