// Portfolio screenshots (1440x900) of the fictional "portfolio-studio" organization.
// Usage: node scripts/portfolio-shots.mjs <password-file> <out-dir> [phase-prefix]
// Seed first: backend> .venv\Scripts\python -m app.cli seed-portfolio <password-file>
import { readFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "@playwright/test";

const [pwFile, outDir, prefix = "p5"] = process.argv.slice(2);
if (!pwFile || !outDir) {
  console.error("Usage: node scripts/portfolio-shots.mjs <password-file> <out-dir> [prefix]");
  process.exit(2);
}
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const password = readFileSync(pwFile, "utf-8").trim();
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const shot = async (name, opts = {}) => {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
  const path = join(outDir, `${prefix}-${name}.png`);
  await page.screenshot({ path, ...opts });
  console.log("saved", path);
};

await page.goto(`${BASE}/login`);
await page.getByLabel("Email").fill("alex.morgan@example.com");
await page.getByLabel("Password").fill(password);
await page.getByRole("button", { name: /log in|sign in/i }).click();
await page.waitForURL(/\/leads$/);
await page.getByRole("button", { name: "Dismiss" }).first().click({ timeout: 1000 }).catch(() => {});
await page.locator("#f-sort").filter({ visible: true }).selectOption("score");
await shot("01-leads-sorted-by-ai-score");

const open = async (name) => {
  await page.goto(`${BASE}/leads`);
  await page.getByRole("link", { name }).filter({ visible: true }).first().click();
  await page.getByRole("heading", { name: "AI analysis" }).filter({ visible: true }).waitFor();
};

await open("Amira Hassan");
await shot("02-lead-ai-analysis-and-score");
await shot("03-lead-ai-analysis-full", { fullPage: true });

await open("Sam Taylor");
await shot("04-prompt-injection-flagged-for-review");

await open("Jordan Pike");
await shot("05-spam-capped");

await open("Nadia Rossi");
await shot("07-ai-unavailable-provisional-fallback");

await page.goto(`${BASE}/settings/scoring`);
await page.getByRole("heading", { name: "Lead scoring" }).waitFor();
await shot("06-scoring-settings", { fullPage: true });

await browser.close();
