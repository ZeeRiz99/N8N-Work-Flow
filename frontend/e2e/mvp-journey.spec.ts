import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

// The 16-step MVP journey (master prompt §12.5), steps 1-15 in the browser. Step 16 (backend
// killed mid-flow) runs in scripts/journey.ps1, which also resets the e2e database before each
// run and starts the backend with the offline AI ("fake provider in CI").
// Needs: E2E_OWNER_EMAIL, E2E_PASSWORD_FILE; the full stack (n8n W1/W4b active, Mailpit).

const MAILPIT = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025";
const OWNER = process.env.E2E_OWNER_EMAIL ?? "";
const PASSWORD_FILE = process.env.E2E_PASSWORD_FILE ?? "";
const visible = (page: Page, name: string | RegExp) =>
  page.getByRole("button", { name }).filter({ visible: true });

async function mailCount(query: string): Promise<number> {
  const r = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(query)}`);
  return ((await r.json()) as { messages_count: number }).messages_count;
}

async function submitForm(page: Page, email: string, name: string) {
  await page.goto("/f/harbor-web");
  await page.getByLabel(/^Full name/).fill(name);
  await page.getByLabel(/^Email/).fill(email);
  await page.getByLabel(/^Company/).fill("Journey Bakery");
  await page.getByLabel(/^What do you need/).selectOption("Website Development");
  await page.getByLabel(/^Budget in USD/).selectOption("$1,500 to $5,000");
  await page.getByLabel(/^When do you need it/).selectOption("Within 1 month");
  await page
    .getByLabel(/^Your message/)
    .fill(
      "We run a bakery and need a new website with online ordering. Budget around $2,000, " +
        "live within a month. Can you send a quote?",
    );
  await page.getByLabel(/may store these details/).check();
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByRole("heading", { name: "Thanks, we have your request" })).toBeVisible();
}

test.skip(!OWNER || !PASSWORD_FILE, "Run through scripts/journey.ps1 (needs E2E_OWNER_EMAIL).");

test("MVP journey: form -> AI score -> alert -> draft -> approve -> sent -> follow-up", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const email = `journey.${stamp}@example.com`;
  const name = `Journey Lead ${stamp}`;

  // 1-3. A visitor submits the public form; the backend stores it and emits the event.
  await submitForm(page, email, name);

  // Log in as the owner.
  await page.goto("/login");
  await page.getByLabel("Email").fill(OWNER);
  await page.getByLabel("Password").fill(readFileSync(PASSWORD_FILE, "utf-8").trim());
  await page.getByRole("button", { name: /log in/i }).click();
  await page.waitForURL(/\/leads$/);

  // 4-7. n8n W1 asks the backend to analyze; the dashboard shows the lead scored High.
  await expect(async () => {
    await page.goto("/leads");
    await page.getByLabel("Search").filter({ visible: true }).fill(email);
    const row = page.getByRole("row").filter({ hasText: name });
    await expect(row.getByText("High")).toBeVisible({ timeout: 4000 });
  }).toPass({ timeout: 90_000, intervals: [3000] });
  await page.getByRole("link", { name }).filter({ visible: true }).first().click();
  const analysis = page.getByRole("region", { name: "AI analysis" }).filter({ visible: true });
  await expect(analysis.getByText("Website Development").first()).toBeVisible();
  await expect(analysis.getByText("“around $2,000”").or(analysis.getByText(/\$2,000/)).first()).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Why this score" }).filter({ visible: true }),
  ).toBeVisible();

  // 8. High lead: the team alert (email until the Telegram bot exists).
  await expect.poll(() => mailCount(`subject:"${name}"`), { timeout: 30_000 }).toBeGreaterThan(0);

  // 9-10. W4 wrote a draft; a person edits and approves it in the Approvals queue.
  await page.goto("/approvals");
  await page.getByRole("button", { name: new RegExp(name) }).click();
  const body = page.getByLabel("Message").filter({ visible: true });
  await body.fill(`${await body.inputValue()}\n\nLooking forward to working with you.`);
  await visible(page, "Approve and send").click();
  await expect(page.getByRole("status").filter({ hasText: /Approved/ })).toBeVisible();

  // 11-12. W4b claims and sends it through SMTP; the draft is marked sent.
  await expect.poll(() => mailCount(`to:${email}`), { timeout: 60_000 }).toBe(1);
  await expect(async () => {
    await page.goto("/approvals");
    await visible(page, "Sent").click();
    await expect(page.getByRole("button", { name: new RegExp(name) })).toBeVisible({
      timeout: 4000,
    });
  }).toPass({ timeout: 30_000, intervals: [2000] });

  // 13. The communication is logged and a follow-up scheduled (timeline + next step).
  await page.goto("/leads");
  await page.getByLabel("Search").filter({ visible: true }).fill(email);
  await page.getByRole("link", { name }).filter({ visible: true }).first().click();
  await expect(page.getByText(/^Email sent:/).filter({ visible: true })).toBeVisible();

  // 14. The Overview reflects the lead and its outcome.
  await page.goto("/overview");
  const latest = page.getByRole("row").filter({ hasText: name });
  await expect(latest.getByText(/^Follow up /)).toBeVisible();

  // 15. Re-submitting the same inquiry creates no duplicate lead and no second send.
  await submitForm(page, email, name);
  await page.waitForTimeout(8000);
  await page.goto("/leads");
  await page.getByLabel("Search").filter({ visible: true }).fill(email);
  await expect(page.getByRole("row").filter({ hasText: name })).toHaveCount(1);
  expect(await mailCount(`to:${email}`)).toBe(1);
});
