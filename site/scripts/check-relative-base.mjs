/** Exercise a Pages subpath without Vite's preview fallback. */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { cp, mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { chromium } from "@playwright/test";

const site = path.resolve(import.meta.dirname, "..");
const temporary = await mkdtemp(path.join(tmpdir(), "homalg-relative-base-"));
const root = path.join(temporary, "project");
await cp(path.join(site, "dist"), root, { recursive: true });
// Synthetic data makes this independent of the private pilot and live registry.
await rm(path.join(root, "data"), { recursive: true, force: true });
await cp(path.join(site, "fixtures/data"), path.join(root, "data"), { recursive: true });
const mime = { ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".html": "text/html", ".svg": "image/svg+xml" };
const server = createServer(async (request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const target = path.resolve(temporary, `.${pathname.endsWith("/") ? pathname + "index.html" : pathname}`);
  try {
    assert(target.startsWith(root + path.sep));
    assert((await stat(target)).isFile());
    response.setHeader("Content-Type", mime[path.extname(target)] || "application/octet-stream");
    response.end(await readFile(target));
  } catch {
    response.writeHead(404).end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  const failed = [];
  const workers = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => { if (response.status() >= 400) failed.push(response.url()); });
  page.on("worker", (worker) => workers.push(worker.url()));
  const base = `http://127.0.0.1:${server.address().port}/project/`;
  await page.goto(`${base}#/doc/Fixture2000`);
  await page.getByRole("tab", { name: "Blueprint", exact: true }).waitFor();
  await page.goto(`${base}#/search?q=Fixture2000.Thm_1`);
  await page.locator(".search-result").waitFor();
  assert.equal(await page.locator(".search-result").count(), 1);
  assert.match(await page.locator(".search-result").innerText(), /Fixture2000.Thm_1/);
  assert(workers.some((url) => /\/project\/assets\/worker-[^/]+\.js$/.test(url)));
  assert.deepEqual(errors, []);
  assert.deepEqual(failed, []);
  console.log(JSON.stringify({ ok: true, base, workers, errors, failed }, null, 2));
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
  await rm(temporary, { recursive: true, force: true });
}
