import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

// UI action audit (master prompt §10.6): every page, every control, no console errors and no
// server errors. Rows in docs/UI_ACTION_AUDIT.md marked "A" are verified here.
// Run with E2E_OWNER_EMAIL / E2E_PASSWORD_FILE set (scripts/ui-audit.ps1 does it).

const OWNER = process.env.E2E_OWNER_EMAIL ?? "";
const PASSWORD_FILE = process.env.E2E_PASSWORD_FILE ?? "";
test.skip(!OWNER || !PASSWORD_FILE, "Run through scripts/ui-audit.ps1.");

const btn = (p: Page, name: string | RegExp) =>
  p.getByRole("button", { name }).filter({ visible: true }).first();
const heading = (p: Page, name: string | RegExp) =>
  p.getByRole("heading", { name, level: 1 }).filter({ visible: true });

test("UI action audit: every page and control works without errors", async ({ page }) => {
  test.setTimeout(300_000);
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
  page.on("response", (r) => {
    if (r.status() >= 500) problems.push(`HTTP ${r.status()} ${r.url()}`);
  });

  // Login
  await page.goto("/login");
  await page.getByLabel("Email").fill(OWNER);
  await page.getByLabel("Password").fill(readFileSync(PASSWORD_FILE, "utf-8").trim());
  await btn(page, /log in/i).click();
  await page.waitForURL(/\/leads$/);

  // Sidebar: every built page opens
  for (const [link, title] of [
    ["Overview", "Overview"],
    ["Leads", "Leads"],
    ["Approvals", "Approvals"],
    ["Duplicates", "Duplicates"],
    ["AI Assistant", "AI Assistant"],
    ["Automation", "Automation"],
    ["Integrations", "Integrations"],
    ["Settings", "Lead scoring"],
  ]) {
    await page.getByRole("link", { name: link, exact: true }).filter({ visible: true }).click();
    await expect(heading(page, title)).toBeVisible();
  }

  // Overview: range buttons and table view
  await page.goto("/overview");
  for (const r of ["30 days", "90 days", "7 days"]) {
    await btn(page, r).click();
    await expect(btn(page, r)).toHaveAttribute("aria-pressed", "true");
  }
  await btn(page, "Show as table").click();
  await expect(page.getByRole("columnheader", { name: "New leads" })).toBeVisible();
  await btn(page, "Show chart").click();

  // Leads: search, filters, sort, new-lead dialog, import link, export
  await page.goto("/leads");
  await page.getByLabel("Search").filter({ visible: true }).fill("Bakery");
  await page.getByLabel("Search").filter({ visible: true }).fill("");
  for (const [label, value] of [
    ["Priority", "high"],
    ["Sort", "score"],
    ["Source", "form"],
    ["Assigned to", "none"],
  ]) {
    await page.getByLabel(label, { exact: true }).filter({ visible: true }).selectOption(value);
  }
  await page.getByLabel("Priority", { exact: true }).filter({ visible: true }).selectOption("");
  await page.getByLabel("Source", { exact: true }).filter({ visible: true }).selectOption("");
  await page.getByLabel("Assigned to", { exact: true }).filter({ visible: true }).selectOption("");
  await btn(page, "New lead").click();
  await expect(page.getByRole("dialog", { name: "New lead" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "New lead" })).toHaveCount(0);
  const exportHref = await page.getByRole("link", { name: "Export" }).getAttribute("href");
  const exp = await page.request.get(exportHref ?? "", {
    headers: { "X-Requested-With": "replyline" },
  });
  expect(exp.status()).toBe(200);
  expect((await exp.text()).split("\n")[0]).toContain("full_name");
  await page.getByRole("link", { name: "Import CSV" }).click();
  await expect(heading(page, /Import/)).toBeVisible();

  // Lead detail: stage, assignee, archive/restore, ask, draft
  await page.goto("/leads");
  await page.getByRole("link", { name: /.+/ }).filter({ visible: true }).locator("xpath=.").first();
  await page.locator("tbody a").filter({ visible: true }).first().click();
  await expect(page.getByRole("heading", { name: "AI analysis" }).filter({ visible: true })).toBeVisible();
  const stage = page.getByLabel("Stage").filter({ visible: true });
  await stage.selectOption({ label: "Qualified" });
  await expect(page.getByRole("status").filter({ hasText: "Stage updated." })).toBeVisible();
  const assignee = page.getByLabel("Assigned to").filter({ visible: true });
  await assignee.selectOption({ index: 1 });
  await expect(page.getByRole("status").filter({ hasText: "Assignment updated." })).toBeVisible();
  await btn(page, "Archive").click();
  await expect(btn(page, "Restore")).toBeVisible();
  await btn(page, "Restore").click();
  await expect(btn(page, "Archive")).toBeVisible();
  await btn(page, "What is their budget?").click();
  await expect(page.getByText(/^From:|do not mention|can only answer/).first()).toBeVisible({
    timeout: 60_000,
  });
  await page.getByLabel("Type").filter({ visible: true }).selectOption("follow_up");
  await page.getByLabel("Type").filter({ visible: true }).selectOption("first_reply");
  await btn(page, /Write a draft/).click();
  await expect(page.getByRole("link", { name: /Review in Approvals/ })).toBeVisible({
    timeout: 60_000,
  });

  // Approvals: select, keyboard, save edits, reject (cancel), tabs
  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: /Automatic checks/ }).first()).toBeVisible();
  await page.locator('[aria-label="Drafts"] button').first().focus();
  await page.keyboard.press("j");
  await page.keyboard.press("k");
  const msg = page.getByLabel("Message").filter({ visible: true });
  await msg.fill(`${await msg.inputValue()}\nThanks again.`);
  await btn(page, "Save edits").click();
  await expect(btn(page, "Save edits")).toBeDisabled();
  await btn(page, "Reject with reason").click();
  await expect(page.getByLabel(/Why reject it/)).toBeVisible();
  await btn(page, "Cancel").click();
  for (const t of ["Sent", "Failed", "Rejected", "Waiting"]) await btn(page, t).click();

  // Duplicates: scan
  await page.goto("/duplicates");
  await btn(page, /Scan/).click();
  await expect(page.getByRole("status").or(page.getByText(/found|new pair|No new/i)).first()).toBeVisible();

  // AI Assistant: playground and lead tab (arrow keys)
  await page.goto("/assistant");
  await btn(page, "Use an example").click();
  await btn(page, /^Analyze$/).click();
  await expect(page.getByText(/Not saved\. Scored/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: "Analyze text" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Ask about a lead" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // Automation and Integrations
  await page.goto("/automation");
  await expect(page.getByRole("link", { name: "Open n8n editor" })).toHaveAttribute("href", /5678/);
  await page.goto("/integrations");
  for (const name of ["n8n automation", "Email (SMTP)"]) {
    const row = page.getByRole("listitem").filter({ hasText: name });
    await row.getByRole("button", { name: "Test connection" }).click();
    await expect(row.getByRole("status")).toContainText("✓");
  }

  // Settings: scoring weights (no save), reset; AI settings save
  await page.goto("/settings/scoring");
  await page.getByLabel("Budget fit").fill("25");
  await expect(page.getByText("Total 105/100")).toBeVisible();
  await expect(btn(page, "Save new version")).toBeDisabled();
  await btn(page, "Reset to recommended").click();
  await expect(page.getByText("Total 100/100")).toBeVisible();
  await page.getByRole("link", { name: "AI", exact: true }).click();
  await btn(page, "Save").click();
  await expect(page.getByRole("status").filter({ hasText: "AI settings saved." })).toBeVisible();

  // Log out
  await btn(page, "Log out").click();
  await page.waitForURL(/\/login/);

  expect(problems, problems.join("\n")).toEqual([]);
});
