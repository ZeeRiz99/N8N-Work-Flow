// P12 portfolio set: 1440x900 PNG + WebP screenshots and an animated GIF of the demo moment
// (public form -> AI processing -> High priority -> score explanation), all on synthetic data.
// Usage: node scripts/final-shots.mjs <email> <password-file> <out-dir> [org-slug]
// Needs the dev stack running (backend, frontend, n8n). No image library: WebP and GIF are
// encoded inside headless Chromium (canvas + the small GIF encoder below).
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "@playwright/test";

const [email, pwFile, outDir, slug = "harbor-web"] = process.argv.slice(2);
if (!email || !pwFile || !outDir) {
  console.error("Usage: node scripts/final-shots.mjs <email> <password-file> <out-dir> [slug]");
  process.exit(2);
}
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const password = readFileSync(pwFile, "utf-8").trim();
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const encoder = await browser.newPage();
const shots = [];
const frames = [];

const settle = async () => {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(500);
};
const shot = async (name) => {
  await settle();
  const buf = await page.screenshot();
  writeFileSync(join(outDir, `${name}.png`), buf);
  shots.push({ name, b64: buf.toString("base64") });
  console.log("saved", name);
  return buf;
};
const frame = async (delayCs, buf) => {
  if (!buf) {
    await settle();
    buf = await page.screenshot();
  }
  frames.push({ b64: buf.toString("base64"), delay: delayCs });
};

// --- 1. the public form (also the first GIF frames)
const lead = {
  name: "Maya Chen",
  email: `maya.chen.${Date.now()}@example.com`,
  company: "Bluebird Bakery",
  message:
    "Hi! We are a family bakery opening a second shop. We need a new website with online " +
    "ordering for cakes and pickup times. Budget is around $3,500 and we would like it live " +
    "within a month, before the holiday rush. Could you send a quote?",
};
await page.goto(`${BASE}/f/${slug}`);
await frame(150);
await page.locator("#full_name").fill(lead.name);
await page.locator("#email").fill(lead.email);
await page.locator("#company").fill(lead.company);
await page.locator("#service").selectOption({ index: 1 });
await page.locator("#budget").selectOption({ index: 2 });
await page.locator("#timeline").selectOption({ index: 1 });
await page.locator("#message").fill(lead.message);
await page.locator("#consent").check();
await frame(200, await shot("10-public-form"));
await page.getByRole("button", { name: /send|submit/i }).click();
await page.getByRole("heading", { name: /Thanks, we have your request/ }).waitFor();
await frame(150);

// --- 2. log in, watch the lead arrive and get analyzed
await page.goto(`${BASE}/login`);
await page.getByLabel("Email").fill(email);
await page.getByLabel("Password").fill(password);
await page.getByRole("button", { name: /log in|sign in/i }).click();
await page
  .waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 })
  .catch(async (e) => {
    await page.screenshot({ path: join(outDir, "_login-failed.png") });
    throw e;
  });
await page.goto(`${BASE}/leads`);
const dismiss = () =>
  page
    .getByRole("button", { name: "Dismiss" })
    .first()
    .click({ timeout: 800 })
    .catch(() => {});
await dismiss();
const leadLink = () =>
  page.getByRole("link", { name: lead.name }).filter({ visible: true }).first();
await leadLink().waitFor({ timeout: 30000 });
await frame(180);

const t0 = Date.now();
let done = false;
let status = "";
while (Date.now() - t0 < 180000) {
  const res = await page.request.get(`${BASE}/api/v1/leads?q=${encodeURIComponent(lead.email)}`);
  const body = await res.json().catch(() => ({}));
  const row = (Array.isArray(body) ? body : (body.items ?? []))[0];
  status = row?.ai_status ?? "";
  if (status === "done" || status === "failed") {
    done = status === "done";
    break;
  }
  await page.waitForTimeout(4000);
}
await page.reload();
await leadLink().waitFor();
console.log(done ? "lead analyzed" : `WARN: AI status "${status}" (shots continue)`);
await frame(200);

// --- 3. lead detail: AI summary with evidence, then the score explanation
await leadLink().click();
await page.getByRole("heading", { name: "AI analysis" }).filter({ visible: true }).waitFor();
await frame(250, await shot("03-lead-ai-summary-evidence"));
await page.locator("#score-h").filter({ visible: true }).first().scrollIntoViewIfNeeded();
await page.evaluate(() => {
  const h = [...document.querySelectorAll("#score-h")].find((e) => e.offsetParent);
  if (h) window.scrollBy(0, h.getBoundingClientRect().top - 90);
});
await frame(300, await shot("04-score-breakdown"));
await page.evaluate(() => window.scrollTo(0, 0));

// --- 4. the rest of the product
const visit = async (path, name, after) => {
  await page.goto(`${BASE}${path}`);
  await dismiss();
  if (after) await after();
  return shot(name);
};
await visit("/overview", "01-overview");
await visit("/leads", "02-leads-filtered", async () => {
  await page.locator("#f-priority").filter({ visible: true }).selectOption("high");
  await page.locator("#f-sort").filter({ visible: true }).selectOption("score");
});
await frame(
  250,
  await visit("/approvals", "05-approvals-draft", async () => {
    const item = page
      .locator('[aria-label="Drafts"] button', { hasText: lead.name })
      .filter({ visible: true })
      .first();
    // W1 writes the draft with a second AI call after the analysis, so it can lag a minute.
    let found = false;
    for (let i = 0; i < 24 && !found; i++) {
      found = await item.isVisible().catch(() => false);
      if (!found) {
        await page.waitForTimeout(5000);
        await page.reload();
        await page.waitForLoadState("networkidle").catch(() => {});
      }
    }
    if (found) await item.click();
    else console.log("WARN: the new lead's draft is not in the queue");
  }),
);
await visit("/automation", "06-automation-center");
await visit("/analytics", "09-analytics-sources");

// --- 5. encode WebP copies and the GIF in the browser
const encode = async (fn, arg) => encoder.evaluate(fn, arg);
for (const s of shots) {
  const b64 = await encode(async (png) => {
    const img = new Image();
    img.src = `data:image/png;base64,${png}`;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.width;
    c.height = img.height;
    c.getContext("2d").drawImage(img, 0, 0);
    return c.toDataURL("image/webp", 0.9).split(",")[1];
  }, s.b64);
  writeFileSync(join(outDir, `${s.name}.webp`), Buffer.from(b64, "base64"));
}

const gif = await encode(
  async ({ frames, w, h }) => {
    // Minimal GIF89a encoder: per-frame popularity palette (256 colours) + LZW.
    const bytes = [];
    const u16 = (v) => bytes.push(v & 255, (v >> 8) & 255);
    const str = (s) => [...s].forEach((ch) => bytes.push(ch.charCodeAt(0)));
    str("GIF89a");
    u16(w);
    u16(h);
    bytes.push(0, 0, 0);
    bytes.push(0x21, 0xff, 0x0b);
    str("NETSCAPE2.0");
    bytes.push(3, 1, 0, 0, 0);
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const ctx = c.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    for (const f of frames) {
      const img = new Image();
      img.src = `data:image/png;base64,${f.b64}`;
      await img.decode();
      ctx.drawImage(img, 0, 0, w, h);
      const px = ctx.getImageData(0, 0, w, h).data;
      const key = new Uint16Array(w * h);
      const counts = new Uint32Array(32768);
      for (let i = 0, p = 0; p < key.length; i += 4, p++) {
        const k = ((px[i] >> 3) << 10) | ((px[i + 1] >> 3) << 5) | (px[i + 2] >> 3);
        key[p] = k;
        counts[k]++;
      }
      const used = [];
      for (let k = 0; k < 32768; k++) if (counts[k]) used.push(k);
      used.sort((a, b) => counts[b] - counts[a]);
      const pal = used.slice(0, 256);
      const rgb = (k) => [((k >> 10) & 31) * 8 + 4, ((k >> 5) & 31) * 8 + 4, (k & 31) * 8 + 4];
      const palRgb = pal.map(rgb);
      const map = new Int16Array(32768).fill(-1);
      pal.forEach((k, i) => (map[k] = i));
      for (const k of used) {
        if (map[k] >= 0) continue;
        const [r, g, b] = rgb(k);
        let best = 0;
        let bd = Infinity;
        palRgb.forEach(([pr, pg, pb], i) => {
          const d = (r - pr) ** 2 * 2 + (g - pg) ** 2 * 4 + (b - pb) ** 2 * 3;
          if (d < bd) {
            bd = d;
            best = i;
          }
        });
        map[k] = best;
      }
      const idx = new Uint8Array(key.length);
      for (let p = 0; p < key.length; p++) idx[p] = map[key[p]];
      bytes.push(0x21, 0xf9, 4, 0x04);
      u16(f.delay);
      bytes.push(0, 0);
      bytes.push(0x2c);
      u16(0);
      u16(0);
      u16(w);
      u16(h);
      bytes.push(0x87);
      for (let i = 0; i < 256; i++) bytes.push(...(palRgb[i] ?? [0, 0, 0]));
      // LZW (same scheme as omggif)
      const min = 8;
      const clear = 1 << min;
      const eoi = clear + 1;
      let size = min + 1;
      let next = eoi + 1;
      let dict = new Map();
      const out = [];
      let cur = 0;
      let bits = 0;
      const emit = (code) => {
        cur |= code << bits;
        bits += size;
        while (bits >= 8) {
          out.push(cur & 255);
          cur >>= 8;
          bits -= 8;
        }
      };
      emit(clear);
      let prefix = idx[0];
      for (let p = 1; p < idx.length; p++) {
        const k = idx[p];
        const kk = (prefix << 8) | k;
        const hit = dict.get(kk);
        if (hit !== undefined) {
          prefix = hit;
          continue;
        }
        emit(prefix);
        if (next === 4096) {
          emit(clear);
          next = eoi + 1;
          size = min + 1;
          dict = new Map();
        } else {
          if (next >= 1 << size) size++;
          dict.set(kk, next++);
        }
        prefix = k;
      }
      emit(prefix);
      emit(eoi);
      if (bits > 0) out.push(cur & 255);
      bytes.push(min);
      for (let i = 0; i < out.length; i += 255) {
        const chunk = out.slice(i, i + 255);
        bytes.push(chunk.length, ...chunk);
      }
      bytes.push(0);
    }
    bytes.push(0x3b);
    let s = "";
    const u8 = Uint8Array.from(bytes);
    for (let i = 0; i < u8.length; i += 32768)
      s += String.fromCharCode(...u8.subarray(i, i + 32768));
    return btoa(s);
  },
  { frames, w: 960, h: 600 },
);
writeFileSync(join(outDir, "demo-moment.gif"), Buffer.from(gif, "base64"));
console.log(`saved demo-moment.gif (${frames.length} frames)`);
await browser.close();
