import { expect, Page, test } from "@playwright/test";

async function go(page: Page, link: string, heading = link) {
  await page.getByRole("link", { name: link, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
}

async function login(page: Page, email = "owner@e2e.test", password = "e2e-owner-password") {
  await page.goto("/login/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

function tomorrow(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() + 86400000));
}

test("owner books a table, sees it on the timeline, checks the guest in", async ({ page }) => {
  await login(page);
  await go(page, "Reservations");
  await page.getByLabel("Day").fill(tomorrow());
  await page.getByRole("button", { name: "New reservation" }).click();
  const dialog = page.getByRole("dialog", { name: "New reservation" });
  await dialog.getByLabel("Phone").fill("9876501234");
  await dialog.getByLabel("Name").fill("Meera Iyer");
  await dialog.getByLabel("Guests").fill("4");
  await dialog.getByLabel("Date").fill(tomorrow());
  await dialog.getByRole("button", { name: "19:30" }).click();
  await dialog.getByLabel("Guest requests").fill("Anniversary");
  await dialog.getByRole("button", { name: "Book table" }).click();
  const row = page.getByRole("row", { name: /Meera Iyer/ });
  await expect(row).toContainText("Confirmed");
  await expect(row).toContainText("P1");
  await go(page, "Tables");
  await page.getByLabel("Day").fill(tomorrow());
  await expect(page.getByTitle(/Meera Iyer · 4 guests · confirmed/)).toBeVisible();
  await go(page, "Reservations");
  await page.getByLabel("Day").fill(tomorrow());
  await page.getByRole("row", { name: /Meera Iyer/ }).getByRole("button", { name: "Arrived" }).click();
  await expect(page.getByRole("row", { name: /Meera Iyer/ })).toContainText("Arrived");
});

test("double booking is refused with nearby alternatives", async ({ page }) => {
  await login(page);
  await page.goto("/reservations/");
  for (const [phone, name] of [["9876501111", "A One"], ["9876502222", "B Two"]]) {
    await page.getByRole("button", { name: "New reservation" }).click();
    const d = page.getByRole("dialog", { name: "New reservation" });
    await d.getByLabel("Phone").fill(phone);
    await d.getByLabel("Name").fill(name);
    await d.getByLabel("Guests").fill("10");
    await d.getByLabel("Date").fill(tomorrow());
    await d.getByLabel("Time", { exact: true }).fill("20:00");
    await d.getByRole("button", { name: "Book table" }).click();
    if (name === "B Two") {
      await expect(d.getByRole("alert")).toContainText(/No table is free/);
      await d.getByRole("button", { name: "Close" }).click();
    }
  }
});

test("menu availability, phone order with server bill, kitchen flow", async ({ page }) => {
  await login(page);
  await go(page, "Menu");
  const lassi = page.locator("div.p-3", { hasText: "Sweet Lassi" });
  await lassi.getByRole("button", { name: "Mark out of stock" }).click();
  await expect(lassi.getByRole("button", { name: "Back in stock" })).toBeVisible();

  const allDay = Object.fromEntries(["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((d) => [d, [["00:00", "23:59"], ["23:59", "00:00"]]]));
  await page.request.patch("/api/settings", { data: { min_payment_type: "none", opening_hours: allDay }, headers: { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "rr_csrf")!.value } });
  await go(page, "Orders");
  await page.getByRole("button", { name: "New phone order" }).click();
  const d = page.getByRole("dialog", { name: "New phone order" });
  await d.getByLabel("Phone").fill("9876503333");
  await d.getByLabel("Name").fill("Arjun");
  await d.getByRole("button", { name: "Start order" }).click();
  const b = page.getByRole("dialog", { name: /Order F/ });
  await b.getByLabel("Dish").selectOption({ label: "Starters: Paneer Tikka - ₹280" });
  await b.getByLabel("Quantity").fill("2");
  await b.getByRole("button", { name: "Add" }).click();
  await expect(b).toContainText("₹560");
  await expect(b.getByRole("row", { name: /Total/ })).toContainText("₹609");
  await b.getByRole("button", { name: "+" }).click();
  await expect(b.getByRole("row", { name: /Total/ })).toContainText("₹903");
  await b.getByRole("button", { name: /send to kitchen/ }).click();
  page.once("dialog", (dlg) => dlg.accept("5"));
  const card = page.locator(".card", { hasText: "Arjun" });
  await card.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("button", { name: "In kitchen" }).click();
  await expect(card).toContainText("Accepted");
  await expect(card).toContainText("Ready by");
  await card.getByRole("button", { name: "Mark ready" }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("button", { name: "Ready", exact: true }).click();
  await card.getByRole("button", { name: "Handed over" }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("button", { name: "Done" }).click();
  await expect(card).toContainText("Completed");
});

test("staff role sees only what it may use, and the API enforces it", async ({ page }) => {
  await login(page, "kitchen@e2e.test", "e2e-kitchen-password");
  await expect(page.getByRole("link", { name: "QR check-in" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Settings" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Staff", exact: true })).toHaveCount(0);
  const csrf = (await page.context().cookies()).find((c) => c.name === "rr_csrf")!.value;
  const r = await page.request.patch("/api/settings", { data: { name: "Hacked" }, headers: { "X-CSRF-Token": csrf } });
  expect(r.status()).toBe(403);
  await go(page, "QR check-in");
  await page.getByPlaceholder("Paste QR link or code").fill("http://localhost:8100/q/not-a-real-token-not-a-real-token-xx");
  await page.getByRole("button", { name: "Look up" }).click();
  await expect(page.getByText("This QR code is not valid for this restaurant.")).toBeVisible();
});

test("settings, holidays and staff management", async ({ page }) => {
  await login(page);
  await go(page, "Settings");
  const profile = page.locator("section", { hasText: "Restaurant profile & GST" });
  await profile.getByLabel("GSTIN").fill("29ABCDE1234F1Z5");
  await profile.getByRole("button", { name: "Save" }).click();
  await expect(profile.getByText("Saved.")).toBeVisible();
  await profile.getByLabel("GSTIN").fill("BAD");
  await profile.getByRole("button", { name: "Save" }).click();
  await expect(profile.getByRole("alert")).toContainText("GSTIN");
  const holidays = page.locator("section", { hasText: "Holidays & special hours" });
  await holidays.getByLabel("Date").fill(tomorrow());
  await holidays.getByPlaceholder("Note (e.g. Diwali)").fill("Staff outing");
  await holidays.getByRole("button", { name: "Add" }).click();
  await expect(holidays).toContainText("Staff outing");
  await go(page, "Staff", "Staff accounts");
  await page.getByRole("button", { name: "Add staff" }).click();
  const d = page.getByRole("dialog", { name: "Add staff" });
  await d.getByLabel("Name").fill("Priya");
  await d.getByLabel("Email").fill("priya@e2e.test");
  await d.getByLabel(/Temporary password/).fill("priya-password-1");
  await d.getByLabel("Role").selectOption("receptionist");
  await d.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("row", { name: /Priya/ })).toBeVisible();
  await go(page, "Usage & health", "Usage & integration health");
  await expect(page.getByText("NOT RUNNING")).toBeVisible();
});
