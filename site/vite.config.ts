import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, createReadStream } from "node:fs";
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import type { Connect } from "vite";

const site = import.meta.dirname;
const base = "./";
/** Serve committed samples only when a generated public dataset is unavailable. */
function fixtures(): Plugin {
  const middleware: Connect.NextHandleFunction = (req, res, next) => {
    if (existsSync(path.join(site, "public/data/manifest.json"))) return next();
    // Vite serves a relative-base build at the preview/dev server root.
    const prefix = "/data/";
    const url = new URL(req.url || "/", "http://localhost");
    if (!url.pathname.startsWith(prefix)) return next();
    let relative: string;
    try {
      relative = decodeURIComponent(url.pathname.slice(prefix.length));
    } catch {
      return next();
    }
    const directory = path.join(site, "fixtures/data");
    const file = path.resolve(directory, relative);
    if (!file.startsWith(`${directory}${path.sep}`) || !existsSync(file))
      return next();
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "no-cache");
    createReadStream(file).pipe(res);
  };
  return {
    name: "homalg-fixture-data",
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
    async closeBundle() {
      await mkdir(path.join(site, "dist"), { recursive: true });
      for (const name of ["LICENSE", "LICENSE-DATA", "NOTICE"]) {
        await copyFile(
          path.join(site, "..", name),
          path.join(site, "dist", name),
        );
      }
    },
  };
}

export default defineConfig({
  base,
  plugins: [react(), tailwindcss(), fixtures()],
  define: {
    __SEARCH_OPTIONS_HASH__: JSON.stringify(
      createHash("sha256")
        .update(readFileSync(path.join(site, "src/data/search/options.mjs")))
        .digest("hex"),
    ),
  },
  worker: { rollupOptions: { output: { name: "HomalgWorker" } } },
  build: {
    manifest: true,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("/node_modules/cytoscape/")) return "vendor-graph";
          if (
            /\/node_modules\/(unified|remark-|rehype-|micromark|mdast-|hast-|katex)/.test(
              id,
            )
          )
            return "vendor-md";
          if (/\/node_modules\/(sigma|graphology)/.test(id))
            return "vendor-sigma";
          if (id.includes("/node_modules/minisearch/")) return "vendor-search";
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
