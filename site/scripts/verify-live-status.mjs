/** Verify a published numeric status through the actual Pages manifest and UI. */
import { chromium } from "playwright";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";

const args = Object.fromEntries(
  process.argv.slice(2).map((arg) => {
    const [key, ...value] = arg.replace(/^--/, "").split("=");
    return [key, value.join("=")];
  }),
);
if (!args.site || !args.expected || !args.out)
  throw new Error("Use --site=URL --expected=STATUS_JSON --out=REPORT_JSON");
const expected = JSON.parse(await readFile(args.expected, "utf8"));
const base = new URL(args.site.endsWith("/") ? args.site : `${args.site}/`);
const manifestUrl = new URL("data/manifest.json", base);
manifestUrl.searchParams.set("verify", String(Date.now()));
const response = await fetch(manifestUrl);
if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
const manifest = await response.json();
const entry = manifest.documents.find(
  (doc) => doc.doc_key === expected.doc_key,
);
if (!entry?.claim.run) throw new Error("Published claim has no run report");
for (const field of ["holder", "generated_at"])
  if (entry.claim.run[field] !== expected[field])
    throw new Error(`Published ${field} differs from the status branch`);
assert.deepEqual(
  entry.claim.run.counts,
  expected.counts,
  "Published numeric counts differ from the status branch",
);

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(new URL("#/claims", base).href);
  const card = page.locator(".claim-card").filter({ hasText: entry.title });
  await card.waitFor();
  const notice = await card.locator(".notice").innerText();
  const reportTime = await page.evaluate(
    (value) => new Date(value).toLocaleString("en"),
    expected.generated_at,
  );
  if (!notice.includes(reportTime))
    throw new Error("UI report timestamp differs");
  const strings = JSON.parse(
    await readFile(new URL("../src/i18n/en.json", import.meta.url), "utf8"),
  );
  const expectedText = strings["claims.counts"]
    .replace("{proved}", String(expected.counts.headline.proof_complete))
    .replace("{pages}", String(expected.counts.pages_reviewed))
    .replace("{issues}", String(expected.open_for_human));
  if (!notice.includes(expectedText))
    throw new Error(`UI counts differ: ${notice}`);
  if (errors.length) throw new Error(errors.join("\n"));
  await mkdir(path.dirname(args.out), { recursive: true });
  await page.screenshot({
    path: args.out.replace(/\.json$/, ".png"),
    fullPage: true,
  });
  const report = {
    verified_at: new Date().toISOString(),
    site: base.href,
    manifest_url: manifestUrl.href,
    manifest_commit: manifest.commit,
    doc_key: expected.doc_key,
    status_generated_at: expected.generated_at,
    counts: expected.counts,
    visible_notice: notice,
    page_errors: errors,
    passed: true,
  };
  await writeFile(args.out, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
