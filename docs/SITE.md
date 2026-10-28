# Website implementation and verification

The website is a Vite, React and TypeScript application with hash routes, English
interface strings, Tailwind CSS and Radix controls. Its data comes through a
single `DataSource` interface; React components consume TanStack Query hooks.
All direct and transitive npm versions are locked in `site/package-lock.json`.
Node 22 or newer is required.

The build fixes Vite `base` to `./`. Hash routes keep asset, worker and data URLs
relative to the document directory, so the same artifact works at a Pages project
subpath, a custom-domain root and local static hosting. No repository-event or
environment-derived base is needed. `file://` is unsupported because module
scripts and data requests require HTTP. After building, run
`node site/scripts/check-relative-base.mjs` to exercise a real static subpath and
the search worker with the synthetic dataset.

## Run locally

```sh
npm ci --prefix site
make fixture-site
npm run dev --prefix site
```

The development and preview servers serve the committed `site/fixtures/data`
when `site/public/data/manifest.json` is absent. These fixtures are generated from
Fixture2000 and Fixture2001, contain 17 nodes, and are synthetic examples. Production
builds use `site/public/data`. Generate deployment data with `homalg site-data`.
The fixture fallback is a server feature, not embedded production sample data.

```sh
npm run generate-types --prefix site -- --check
npm run lint --prefix site
npm test --prefix site
npm run build --prefix site
npm exec --prefix site -- playwright install chromium
npm run test:e2e --prefix site
```

`npm run build` type-checks the application and checks compressed JavaScript,
total deployment size, the single ELK worker and the single KaTeX version.
`site/budgets.json` holds limits: 200 KiB initial JavaScript gzip, 400 KiB per
lazy route and 900 MiB total site files. The initial total includes statically
imported vendor chunks. Graph, Markdown and Sigma code are lazy chunks.

## Routes and behavior

- `#/`: document cards, counts, claim summaries and search.
- `#/doc/:docKey`, `/fidelity`, `/list` and `/node/:localId`: document Blueprint,
  fidelity audit, keyboard-accessible list and route-controlled details.
- `#/node/:docKey/:localId`: standalone node details.
- `#/search`: shareable query and facets, dependency search and pagination.
- `#/tags/:id?`, `#/concepts/:id?`, `#/timeline`: taxonomy, concept history and
  document graph, comparable concept lanes, definition comparisons, versioned summaries, a table or a Sigma global dependency view.
- `#/claims` and `#/about`: effective claim expiry, counts, build information,
  data downloads, health diagnostics and licenses.

Desktop node details are an aside. Mobile details use a modal Radix dialog and
mobile document pages initially select List. The list is the accessible graph
alternative on all screen sizes and virtualizes above 500 rows. Graph controls,
search, theme selection and drawers support keyboard navigation. The skip link
focuses the main region without changing the hash route. Reduced-motion settings
replace graph animation with immediate fitting.

The Blueprint preserves dependency direction, chapter grouping and verified versus
declared edges. `contractAux` projects collapsed helper nodes onto their parents,
combines duplicate edges and preserves `via` evidence. Bridges and cited nodes
remain visible. Clicking a parent with collapsed auxiliaries expands them;
the selected parent also has an accessible expansion button. Auxiliary and chapter
state persist per document in session storage. Node deep links override collapse.
Default positions come from the document bundle; changed views use an isolated
ELK worker and best-effort IndexedDB caching. Large documents initially collapse
chapters. Context actions include identifiers, source links and dependency search;
PNG and Mermaid export describe the displayed graph.

The page theme follows the system or a persisted manual choice. Shiki signatures
and full source use separate light and dark CSS variables. The graph map keeps a
light canvas in both page themes so its status colors remain stable. Node text
has at least 4.5:1 contrast and outlines at least 3:1 against the canvas and chapter
backgrounds, tested from the actual Cytoscape style definitions. This applies the
WCAG boundary alternative: the specification's simultaneous white/pale fills and
3:1 *fill* contrast against a light canvas cannot both be met. Pruned node fills
are translucent while labels retain full contrast. Color is also encoded by glyphs,
outline patterns, shapes and text badges.

## Data and generated artifacts

`site/src/data/types.ts` is generated from all JSON schemas; do not edit it.
`site/scripts/generate-types.mjs --check` detects drift. Conditional schema rules
remain runtime constraints; the generator's TypeScript projection removes schema
conditionals that json-schema-to-typescript otherwise incorrectly reduces to
unknown fields, and translates tuple spelling for the generator.

Static mode fetches the manifest with `cache: no-cache`, rejects unsupported schema
versions before opening routes, caches documents by graph hash and nodes by build
commit, and reloads the manifest once after a content-hash 404. A second failure
shows a redeployment error. Search uses a MiniSearch worker, hash-keyed IndexedDB
cache and a prebuilt index when its options hash matches the compiled tokenizer.
Otherwise the worker builds from search shards. Full node identifiers and Lean
names and local identifiers such as `Thm_1` remain searchable as complete tokens; taxonomy facets include descendants.
Dependency traversal lazily loads external document bundles, caps depth at three
and returns at most 500 nodes with a truncation notice.

To select the API adapter, use `?source=api&api=http://127.0.0.1:8000` before the
hash, or configure the Vite environment variables documented in
`site/src/data/loaders.ts`. `ApiSource` expects the same schema records as static
mode. Its search result contract is `{records,total,page,page_size,facets,truncated}`;
query keys are exactly the hash-search keys. `neighbors` returns dependency edge
arrays; `up` means dependencies and `down` means dependents. Live browser tests run against an actual SQLite/FastAPI snapshot. Above 5,000
nodes in API mode, the document first requests `?chapter=` for metadata and chapter
IDs only, then requests the selected chapter. `__unsectioned__` selects items
without a chapter. The sidebar retains all chapter names while the graph receives
only the selected chapter's membership map. The `X-Homalg-Truncated` response
header preserves dependency-closure limits.

Prerender automatically partitions serialized MiniSearch indexes per document
above 50,000 records or a 30 MB global index. The additive optional manifest field
`documents[].files.search_index` names each index. A document-filtered query loads
only that document's records/index; an unscoped query still searches every record
and builds a combined index when there is no global serialized index. API mode is
preferred for large global searches. Browser worker scopes are bounded, and
IndexedDB keys include data and tokenizer hashes. Test-only threshold overrides
are `HOMALG_SEARCH_SHARD_NODES` and `HOMALG_SEARCH_SHARD_BYTES`.

The Python pipeline calls:

```sh
node site/scripts/prerender.mjs --data <site-data-directory>
```

The script shares the tokenizer, auxiliary contraction, ELK options and Markdown
pipeline with the browser. It adds dual-theme Shiki HTML, a serialized MiniSearch
index and search-options hash, default auxiliary-collapsed layouts, and Markdown
health diagnostics. `--skip shiki,search,layout,markdown` allows individual stages
to be disabled. Each ELK attempt runs in a terminable worker: a 180-second timeout
retries using browser settings, then records `layout: null` and
`manifest.prerender.layout_failed` without blocking deployment. The browser then
computes positions. `HOMALG_LAYOUT_TIMEOUT_MS` exists for deterministic timeout
testing. JSON writes are atomic and deterministically sorted.

The Markdown pipeline sanitizes before KaTeX output, disables remote images,
links known node identifiers, and records malformed math or unknown node links.
The same parser generates build diagnostics and browser output. No external
font or script CDNs are required.

## Measured verification

The October 2026 implementation run used the committed two-document fixtures:

- 31 Vitest tests cover source parity, schema-version rejection, redeployment,
  search round trips, exact identifiers, filters, 20,000-record first query,
  auxiliary projection, graph ordering, hostile Markdown, math/link diagnostics,
  runtime claim expiry, layout timeout fallback, document search sharding, merged
  decade shards, API overview/truncation, translations and graph contrast.
- 16 Playwright tests cover real API browsing, chapter-only requests, evolution
  review isolation and provenance, plus static browsing, deep links, parent expansion persistence, both Shiki
  themes, mobile dialog focus and deployment replacement. Axe checks all six
  required routes and the dark document view for serious/critical violations.
- Lighthouse 13 reported accessibility 100 for the home page.
- The initial production JavaScript was approximately 144 KiB gzip; one isolated
  ELK worker and one KaTeX version were emitted. The fixture-free application was
  approximately 4.3 MiB. `npm audit` reported zero vulnerabilities at that run.
- `node site/scripts/benchmark-layout.mjs` measured 2.52 seconds for 2,000 nodes
  arranged as 100 parallel dependency chains across ten chapters, including
  worker startup. The 3-second budget passed on this machine. `--enforce` makes
  the budget an exit-code check.
- `--chain` is an adversarial single 2,000-node chain: it measured 4.86 seconds and
  exceeds the recomputation target. The worker keeps this work off the UI thread;
  precomputation avoids it on the normal initial view. Performance depends on
  topology and hardware.
- `node site/scripts/benchmark-browser.mjs` serves gzip-compressed synthetic data
  over real loopback HTTP, creates a fresh Chromium 156 context, and measures the
  first actual Cytoscape render from navigation start. The 2,000-node default
  chapter-collapse view measured 464–468 ms in two consecutive runs against the 500 ms budget. All ten chapter
  summaries and nine aggregated dependencies are present. The optional expanded
  view displays all 2,000 nodes and measured 1,231–1,249 ms; it does not meet 500 ms.
- Adding `--api=http://127.0.0.1:8789` uses the persistent real 100,000-node SQLite
  database: chapter overview measured 886–890 ms from navigation, and selecting a
  chapter painted its 1,000 nodes and 999 dependencies in 618–625 ms, both below the
  1-second target. Without precomputed positions, a complete dependency-rank
  layout paints immediately while the ELK worker refines it. The metric is the
  actual graph render, not the loading indicator. The server received only the
  overview and selected chapter requests.
- `build/browser-benchmark.json` retains timing breakdowns and measured counts.
  `--enforce` checks the default static view and, when requested, both API views.
  Expanded graphs and the single-chain ELK stress result remain reported
  limitations. These are local-machine measurements rather than a guarantee for
  every topology, network or device.

No remote deployment is implied by these local checks. The real two-source
evolution rehearsal is documented in [evolution/README.md](evolution/README.md).
