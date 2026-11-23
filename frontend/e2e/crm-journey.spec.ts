import { expect, type Page, test } from "@playwright/test";

// Next.js 16 keeps the previous page mounted but hidden (React Activity), so match visible only.
const label = (page: Page, text: string | RegExp) =>
  page.getByLabel(text).filter({ visible: true });

// Phase 4 gate: register -> create lead -> change stage -> add note -> import CSV -> export.
// Synthetic data only (example.com).
test("CRM journey: login, lead, stage, note, CSV import, export", async ({ page }) => {
  const stamp = Date.now();
  const email = `e2e.${stamp}@example.com`;

  // 1. Create an account (development sign-up) and land on Leads.
  await page.goto("/register");
  await page.getByLabel("Business name").fill(`E2E Test ${stamp}`);
  await page.getByLabel("Your name").fill("E2E Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("E2e-Journey-2026");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/leads$/);
  await expect(page.getByRole("heading", { name: "Leads" })).toBeVisible();
  // The name also appears in the "Assigned to" filter, so look in the user menu.
  await expect(page.getByRole("strong").filter({ hasText: "E2E Owner" })).toBeVisible();

  // 2. Add a lead by hand; it opens its detail page.
  await page.getByRole("button", { name: "New lead" }).click();
  const dialog = page.getByRole("dialog", { name: "New lead" });
  await dialog.getByLabel(/^Name/).fill("Grace Mensah");
  await dialog.getByLabel(/^Email/).fill(`grace.${stamp}@example.com`);
  await dialog.getByLabel(/^Company/).fill("Bloom Florals");
  await dialog.getByRole("button", { name: "Add lead" }).click();
  await expect(page.getByRole("heading", { name: "Grace Mensah" })).toBeVisible();
  await expect(label(page, "Stage")).toHaveValue(/.+/);

  // 3. Move it to Qualified.
  await label(page, "Stage").selectOption({ label: "Qualified" });
  await expect(page.getByRole("status").filter({ hasText: "Stage updated." })).toBeVisible();
  await expect(page.getByText("Moved to Qualified").filter({ visible: true })).toBeVisible();

  // 4. Add a note (rendered as plain text, so the tags stay visible as text).
  await label(page, "Add a note for your team").fill("Asked for a quote <b>today</b>.");
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.getByText("Asked for a quote <b>today</b>.")).toBeVisible();
  await expect(page.getByText("Note added").filter({ visible: true })).toBeVisible();

  // 5. Import two leads from CSV: preview first, then confirm.
  await page.goto("/leads/import");
  const csv = [
    "Name,Email,Company,Notes",
    `Hina Qureshi,hina.${stamp}@example.com,Qureshi Interiors,Wants a booking system`,
    `Olivia Chen,olivia.${stamp}@example.com,Northwind Realty,`,
    `,broken.${stamp}@example.com,No Name Ltd,`,
  ].join("\n");
  await label(page, "CSV file").setInputFiles({
    name: "leads.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf-8"),
  });
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview.getByText("New leads")).toBeVisible();
  await expect(preview.getByText("Name is empty.")).toBeVisible();
  await preview.getByRole("button", { name: "Import 2 rows" }).click();
  await expect(page.getByText("2 new leads, 0 updated, 1 skipped.")).toBeVisible();

  // 6. The list shows them, and search narrows it down.
  await page.getByRole("link", { name: "View leads" }).click();
  await expect(page.getByRole("link", { name: "Hina Qureshi" })).toBeVisible();
  await label(page, "Search").fill("Northwind");
  await expect(page.getByRole("link", { name: "Olivia Chen" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Hina Qureshi" })).toHaveCount(0);

  // 7. Export (owner) downloads a CSV with the leads and safe cells.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Export" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^leads-.*\.csv$/);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  const text = Buffer.concat(chunks).toString("utf-8");
  expect(text).toContain("full_name,email");
  expect(text).toContain("Grace Mensah");
  expect(text).toContain("Olivia Chen");
});
