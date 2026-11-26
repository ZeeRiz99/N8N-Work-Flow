import { readFileSync, writeFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Automated WCAG 2.1 A/AA scan of every page (P10). Fails on critical issues; serious and
// moderate ones are written to test-results/axe-report.json for triage in docs/SECURITY.md.
// Run through scripts/ui-audit.ps1 (it creates and removes a temporary owner).

const OWNER = process.env.E2E_OWNER_EMAIL ?? "";
const PASSWORD_FILE = process.env.E2E_PASSWORD_FILE ?? "";
test.skip(!OWNER || !PASSWORD_FILE, "Run through scripts/ui-audit.ps1.");

const PAGES = [
  "/overview",
  "/leads",
  "/approvals",
  "/duplicates",
  "/follow-ups",
  "/assistant",
  "/automation",
  "/analytics",
  "/integrations",
  "/settings/scoring",
  "/settings/ai",
  "/settings/team",
  "/settings/pipeline",
  "/settings/services",
  "/settings/rules",
];

test("axe: no critical accessibility issues on any page", async ({ page, browser }) => {
  test.setTimeout(240_000);
  const findings: { page: string; id: string; impact: string; nodes: number; help: string }[] = [];
  const scan = async (path: string, p = page) => {
    const r = await new AxeBuilder({ page: p })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    for (const v of r.violations) {
      findings.push({
        page: path,
        id: v.id,
        impact: v.impact ?? "unknown",
        nodes: v.nodes.length,
        help: v.help,
      });
    }
  };

  // Public pages first (logged out).
  const ctx = await browser.newContext({
    baseURL: test.info().project.use.baseURL ?? "http://localhost:3000",
  });
  const anon = await ctx.newPage();
  for (const path of ["/login", "/register", "/f/harbor-web"]) {
    await anon.goto(path);
    await anon.waitForLoadState("networkidle");
    await scan(path, anon);
  }
  await ctx.close();

  await page.goto("/login");
  await page.getByLabel("Email").fill(OWNER);
  await page.getByLabel("Password").fill(readFileSync(PASSWORD_FILE, "utf-8").trim());
  await page.getByRole("button", { name: /log in/i }).click();
  await page.waitForURL(/\/leads$/);
  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(300);
    await scan(path);
  }
  await page.goto("/leads");
  await page.locator("tbody a").filter({ visible: true }).first().click();
  await page.getByRole("heading", { name: "AI analysis" }).filter({ visible: true }).waitFor();
  await scan("/leads/[id]");

  writeFileSync("test-results/axe-report.json", JSON.stringify(findings, null, 2));
  const critical = findings.filter((f) => f.impact === "critical");
  expect(critical, JSON.stringify(critical, null, 2)).toEqual([]);
});
