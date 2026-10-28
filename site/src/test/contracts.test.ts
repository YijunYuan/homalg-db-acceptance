// @vitest-environment node
import { describe, expect, it } from "vitest";
import { readFile, cp, mkdtemp, rm } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { tmpdir } from "node:os";
import path from "node:path";
import { StaticJsonSource } from "../data/static";
import { ApiSource } from "../data/api";
import { DataError, type SearchQuery } from "../data/source";
import {
  createIndex,
  runSearch,
  type SerializedIndex,
} from "../data/search/engine";
import {
  contractAux,
  aggregateEdges,
  defaultCollapsed,
  toMermaid,
} from "../data/graph/contract.mjs";
import { seedPositions } from "../data/graph/seed.mjs";
import { graphInput } from "../../scripts/layout.mjs";
import { markdownProcessor } from "../components/markdown/pipeline.mjs";
import { claimState } from "../data/claims";
import type {
  SearchRecord,
  SiteManifest,
  SiteDocumentBundle,
} from "../data/types";
const fixtures = path.resolve(import.meta.dirname, "../../fixtures/data");
const read = async <T>(file: string): Promise<T> =>
  JSON.parse(await readFile(path.join(fixtures, file), "utf8"));
const manifest = await read<SiteManifest>("manifest.json");
const docs = new Map(manifest.documents.map((doc) => [doc.doc_key, doc]));
const records = (
  await Promise.all(
    manifest.documents.map((doc) =>
      read<SearchRecord[]>(doc.files.search_shard),
    ),
  )
).flat();
const runner = async () => {
  let index: Awaited<ReturnType<typeof createIndex>>, items: SearchRecord[];
  return {
    async init(
      values: SearchRecord[],
      _hash: string,
      serialized?: SerializedIndex,
    ) {
      items = values;
      index = await createIndex(items, serialized);
      return true;
    },
    async query(query: SearchQuery) {
      return runSearch(index, items, query);
    },
  };
};
const staticFetch: typeof fetch = async (input) => {
  const url = String(input),
    file = url.split("/data/")[1];
  try {
    return new Response(JSON.stringify(await read(file)), { status: 200 });
  } catch {
    return new Response("", { status: 404 });
  }
};
const staticSource = () =>
  new StaticJsonSource("/homalg-db/", staticFetch, runner);
const apiFetch: typeof fetch = async (input) => {
  const url = new URL(String(input)),
    route = url.pathname.replace("/api/", ""),
    parts = route.split("/");
  try {
    let data: unknown;
    if (route === "manifest") data = manifest;
    else if (parts[0] === "documents")
      data = await read(docs.get(parts[1])!.files.document);
    else if (parts[0] === "nodes" && parts[3] === "neighbors")
      data = await staticSource().neighbors(
        `${parts[1]}.${parts[2]}`,
        url.searchParams.get("dir") as "up" | "down",
        Number(url.searchParams.get("depth")),
      );
    else if (parts[0] === "nodes")
      data = await read(`nodes/${parts[1]}/${parts[2]}.json`);
    else if (parts[0] === "search")
      data = await staticSource().search(Object.fromEntries(url.searchParams));
    else if (parts[0] === "global-dag")
      data = await read(
        manifest.global_dag_files.find(
          (file) =>
            file.from === Number(url.searchParams.get("from")) &&
            file.to === Number(url.searchParams.get("to")),
        )!.file,
      );
    else data = await read(`${route}.json`);
    return new Response(JSON.stringify(data));
  } catch {
    return new Response("", { status: 404 });
  }
};
describe("DataSource parity", () => {
  for (const [name, make] of [
    ["static", staticSource],
    ["api", () => new ApiSource("https://example.test", apiFetch)],
  ] as const) {
    it(`${name}: reads the public contracts`, async () => {
      const source = make();
      expect((await source.manifest()).schema_version).toBe(1);
      const doc = await source.document("Fixture2000");
      expect(doc.nodes.some((node) => node.local_id === "Thm_1")).toBe(true);
      expect((await source.node("Fixture2000.Thm_1")).summary.id).toBe(
        "Fixture2000.Thm_1",
      );
      expect((await source.search({ q: "chain" })).total).toBeGreaterThan(0);
      expect((await source.taxonomy()).tags.length).toBe(109);
      expect((await source.globalGraph()).documents.length).toBe(2);
      expect(await source.evolution("unpublished-concept")).toBeNull();
      expect(await source.health()).toHaveProperty("markdown_findings");
    });
    it(`${name}: traverses cross-document dependencies`, async () => {
      const source = make(),
        node = (await source.document("Fixture2001")).nodes.find(
          (node) => node.local_id === "Thm_1",
        )!;
      const edges = await source.neighbors(node.id, "up", 3);
      expect(edges.some((edge) => edge.to.startsWith("Fixture2000."))).toBe(
        true,
      );
      expect(edges.every((edge) => edge.from !== edge.to)).toBe(true);
    });
  }
  it("has matching query results and facets", async () => {
    const one = await staticSource().search({ q: "chain", sort: "id" }),
      two = await new ApiSource("https://example.test", apiFetch).search({
        q: "chain",
        sort: "id",
      });
    expect(two).toEqual(one);
  });
  it("revalidates manifest and recovers once from an old content hash", async () => {
    const calls: { file: string; cache?: RequestCache }[] = [];
    let reload = false;
    const entry = manifest.documents[0],
      updated = structuredClone(manifest);
    updated.documents[0].files.document = "documents/new.json";
    const fetcher: typeof fetch = async (input, init) => {
      const file = String(input).split("/data/")[1];
      calls.push({ file, cache: init?.cache });
      if (file === "manifest.json") {
        if (init?.cache === "reload") reload = true;
        return new Response(JSON.stringify(reload ? updated : manifest));
      }
      if (file === entry.files.document)
        return new Response("", { status: 404 });
      if (file === "documents/new.json")
        return new Response(JSON.stringify(await read(entry.files.document)));
      return new Response("", { status: 404 });
    };
    const source = new StaticJsonSource("/nested/", fetcher, runner);
    expect((await source.document(entry.doc_key)).document.doc_key).toBe(
      entry.doc_key,
    );
    expect(
      calls
        .filter((call) => call.file === "manifest.json")
        .map((call) => call.cache),
    ).toEqual(["no-cache", "reload"]);
  });
  it("fails with the redeployed banner code after the second 404", async () => {
    const fetcher: typeof fetch = async (input) =>
      String(input).endsWith("manifest.json")
        ? new Response(JSON.stringify(manifest))
        : new Response("", { status: 404 });
    await expect(
      new StaticJsonSource("/", fetcher).document("Fixture2000"),
    ).rejects.toMatchObject({ code: "redeployed" });
  });
  it("stops loading unsupported schemas", async () => {
    let calls = 0;
    const fetcher: typeof fetch = async () => {
      calls++;
      return new Response(JSON.stringify({ ...manifest, schema_version: 99 }));
    };
    await expect(
      new StaticJsonSource("/", fetcher).document("Fixture2000"),
    ).rejects.toBeInstanceOf(DataError);
    expect(calls).toBe(1);
  });
});
describe("search serialization", () => {
  it("returns identical results for ten queries before and after serialization", async () => {
    const fresh = await createIndex(records),
      loaded = await createIndex(records, fresh.toJSON());
    for (const q of [
      "chain",
      "complex",
      "Fixture2000.Thm_1",
      "Thm_2",
      "degree",
      "zero",
      "homology",
      "Nat",
      "definition",
      "fixture",
    ])
      expect(runSearch(loaded, records, { q })).toEqual(
        runSearch(fresh, records, { q }),
      );
  });
  it("does not confuse neighboring whole identifiers", async () => {
    const index = await createIndex(records);
    const result = runSearch(index, records, { q: "Fixture2000.Thm_1" });
    expect(result.records.map((record) => record.id)).toContain(
      "Fixture2000.Thm_1",
    );
    expect(result.records.map((record) => record.id)).not.toContain(
      "Fixture2000.Thm_2",
    );
  });
  it("finds local identifiers without confusing them with auxiliary names", async () => {
    const index = await createIndex(records);
    const ids = runSearch(index, records, { q: "Thm_1" }).records.map(
      (record) => record.id,
    );
    expect(ids).toContain("Fixture2000.Thm_1");
    expect(ids).not.toContain("Fixture2000.Aux_Thm_1_step");
    expect(ids).not.toContain("Fixture2000.Thm_2");
  });
  it("indexes author arrays as names and filters statuses", async () => {
    const record = {
      ...records[0],
      id: "Fixture2000.Thm_99",
      authors: ["Ada Lovelace"],
      headline: "proof-complete" as const,
    };
    const index = await createIndex([record]);
    expect(runSearch(index, [record], { q: "Lovelace" }).total).toBe(1);
    expect(runSearch(index, [record], { headline: "in-progress" }).total).toBe(
      0,
    );
  });
  it("queries a 20,000-node prebuilt index within one second", async () => {
    const large = Array.from({ length: 20000 }, (_, i) => ({
      ...records[i % records.length],
      id: `Fixture2000.Thm_${i}`,
      title: `Complex example ${i}`,
    }));
    const built = await createIndex(large),
      loaded = await createIndex(large, built.toJSON());
    const start = performance.now();
    const result = runSearch(loaded, large, { q: "complex" });
    expect(result.total).toBeGreaterThan(1000);
    expect(performance.now() - start).toBeLessThan(1000);
  }, 30_000);
});
describe("graph projection", () => {
  it("contracts both endpoints, combines classifications and preserves intermediary nodes", async () => {
    const bundle = await read<SiteDocumentBundle>(
        docs.get("Fixture2000")!.files.document,
      ),
      aux = bundle.nodes.find((node) => node.local_id === "Aux_Thm_1_step")!;
    const edges = [
      {
        from: aux.aux_parent!,
        to: aux.id,
        kind: "proof" as const,
        declared: true,
        verified: false,
      },
      {
        from: aux.id,
        to: "Fixture2000.Def_1",
        kind: "proof" as const,
        declared: true,
        verified: true,
      },
      {
        from: aux.aux_parent!,
        to: "Fixture2000.Def_1",
        kind: "statement" as const,
        declared: false,
        verified: true,
      },
    ];
    expect(
      contractAux(bundle.nodes, edges, defaultCollapsed(bundle.nodes)),
    ).toEqual([
      {
        from: aux.aux_parent,
        to: "Fixture2000.Def_1",
        kind: "statement",
        declared: true,
        verified: true,
        via: [aux.id],
      },
    ]);
  });
  it("builds flat chapter partitions and dependency-first arrows", () => {
    const nodes = [
        { id: "A", label: "A" },
        { id: "B", label: "B" },
      ],
      edges = [
        { from: "B", to: "A", kind: "proof", declared: true, verified: true },
      ];
    const input = graphInput(nodes, edges, [
      { node_ids: ["A"] },
      { node_ids: ["B"] },
    ]);
    expect(
      input.children.map(
        (node: { layoutOptions: Record<string, string> }) =>
          node.layoutOptions["elk.partitioning.partition"],
      ),
    ).toEqual(["1", "2"]);
    expect(input.edges[0]).toMatchObject({ sources: ["A"], targets: ["B"] });
    expect(toMermaid(nodes, edges)).toContain("n0 --> n1");
  });
});
describe("Markdown and claims", () => {
  it("sanitizes HTML, preserves math and links node identifiers", () => {
    const file = markdownProcessor().processSync(
      "<script>alert(1)</script>\n\n$H_n(C)$ and `Fixture2000.Thm_1`",
    );
    expect(String(file)).not.toContain("<script");
    expect(String(file)).toContain("katex");
    expect(String(file)).toContain("#/node/Fixture2000/Thm_1");
  });
  it("reports malformed math without breaking the page", () => {
    const file = markdownProcessor().processSync("$\\frac{$");
    expect(String(file)).toContain("katex-error");
    expect(
      file.messages.some(
        (message: { ruleId?: string }) => message.ruleId === "parseerror",
      ),
    ).toBe(true);
  });
  it("reports unresolved node links", () => {
    const file = markdownProcessor({ nodeIds: new Set() }).processSync(
      "`Fixture2000.Thm_1`",
    );
    expect(file.messages[0].ruleId).toBe("dangling-node-link");
  });
  it("expires claims using the effective expiry on the client", () => {
    expect(
      claimState(
        {
          state: "active",
          expires_at: "2000-01-01T00:00:00Z",
          effective_expires_at: "2000-01-10T00:00:00Z",
        },
        Date.parse("2000-01-05"),
      ),
    ).toBe("active");
    expect(
      claimState(
        { state: "active", effective_expires_at: "2000-01-10T00:00:00Z" },
        Date.parse("2000-01-11"),
      ),
    ).toBe("expired");
  });
});
it("layout timeouts produce a usable deployment and explicit fallback", async () => {
  const temporary = await mkdtemp(path.join(tmpdir(), "homalg-prerender-"));
  try {
    await cp(fixtures, temporary, { recursive: true });
    await promisify(execFile)(
      process.execPath,
      [
        path.resolve(import.meta.dirname, "../../scripts/prerender.mjs"),
        "--data",
        temporary,
        "--skip",
        "shiki,search,markdown",
      ],
      {
        env: { ...process.env, HOMALG_LAYOUT_TIMEOUT_MS: "1" },
        timeout: 45_000,
      },
    );
    const result = JSON.parse(
      await readFile(path.join(temporary, "manifest.json"), "utf8"),
    );
    expect(result.prerender.layout_failed).toEqual(
      manifest.documents.map((doc) => doc.doc_key),
    );
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}, 60_000);

it("partitions large search indexes and loads only a requested document", async () => {
  const temporary = await mkdtemp(path.join(tmpdir(), "homalg-search-shards-"));
  try {
    await cp(fixtures, temporary, { recursive: true });
    await promisify(execFile)(
      process.execPath,
      [
        path.resolve(import.meta.dirname, "../../scripts/prerender.mjs"),
        "--data",
        temporary,
        "--skip",
        "shiki,layout,markdown",
      ],
      {
        env: { ...process.env, HOMALG_SEARCH_SHARD_NODES: "1" },
        timeout: 45_000,
      },
    );
    const result: SiteManifest = JSON.parse(
      await readFile(path.join(temporary, "manifest.json"), "utf8"),
    );
    expect(result.search_index_file).toBeUndefined();
    expect(
      result.documents.every((doc) =>
        doc.files.search_index?.startsWith("search-index/"),
      ),
    ).toBe(true);
    const requested: string[] = [];
    const fetcher: typeof fetch = async (input) => {
      const file = String(input).split("/data/")[1];
      requested.push(file);
      return new Response(await readFile(path.join(temporary, file), "utf8"), {
        status: 200,
      });
    };
    const source = new StaticJsonSource("/", fetcher, runner);
    const response = await source.search({ doc: "Fixture2000", q: "Thm_1" });
    expect(response.records.map((record) => record.id)).toEqual([
      "Fixture2000.Thm_1",
    ]);
    expect(requested).toContain(result.documents[0].files.search_index);
    expect(requested).not.toContain(result.documents[1].files.search_shard);
    expect(requested).not.toContain(result.documents[1].files.search_index);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}, 60_000);

it("requests API chapter overviews explicitly and preserves closure truncation", async () => {
  const urls: string[] = [];
  const api = new ApiSource("http://localhost:8787", async (input) => {
    urls.push(String(input));
    return new Response("[]", { headers: { "X-Homalg-Truncated": "true" } });
  });
  await api.document("Fixture2000", "");
  expect(urls[0]).toMatch(/\/api\/documents\/Fixture2000\?chapter=$/);
  const edges = await api.neighbors("Fixture2000.Thm_1", "up", 10);
  expect(edges.truncated).toBe(true);
  expect(urls[1]).toMatch(/neighbors\?dir=up&depth=3$/);
});

it("merges decade shards and preserves cross-decade edges", async () => {
  const first = {
    id: "Fixture2000.Thm_1",
    doc: "Fixture2000",
    year: 2000,
    kind: "theorem",
    headline: "in-progress",
    status: "stated",
    x: 0,
    y: 0,
  };
  const second = {
    ...first,
    id: "Fixture2010.Thm_1",
    doc: "Fixture2010",
    year: 2010,
    x: 10,
  };
  const edge = { from: second.id, to: first.id, verified: true };
  const data = new Map<string, unknown>([
    [
      "manifest.json",
      {
        ...manifest,
        global_dag_files: [
          { from: 2000, to: 2009, file: "first.json" },
          { from: 2010, to: 2019, file: "second.json" },
        ],
      },
    ],
    ["first.json", { range: [2000, 2009], nodes: [first], edges: [] }],
    ["second.json", { range: [2010, 2019], nodes: [second], edges: [edge] }],
  ]);
  const source = new StaticJsonSource(
    "/",
    async (input) =>
      new Response(JSON.stringify(data.get(String(input).split("/data/")[1]))),
  );
  expect(await source.globalDag([2000, 2019])).toEqual({
    range: [2000, 2019],
    nodes: [first, second],
    edges: [edge],
  });
  expect((await source.globalDag([2000, 2009])).nodes).toEqual([first]);
});

it("aggregates projected chapter edges while preserving dependency flags", () => {
  const projected = Array.from({ length: 900 }, (_, i) => ({
    from: `chapter:${2 + Math.floor(i / 100)}`,
    to: `chapter:${1 + Math.floor(i / 100)}`,
    kind: i % 2 ? "proof" : "statement",
    declared: i % 2 === 0,
    verified: i % 2 === 1,
  }));
  const edges = aggregateEdges(projected);
  expect(edges).toHaveLength(9);
  expect(
    edges.every(
      (edge: {
        aggregate_count: number;
        declared: boolean;
        verified: boolean;
      }) => edge.aggregate_count === 100 && edge.declared && edge.verified,
    ),
  ).toBe(true);
});

it("paints a complete dependency-ordered seed before worker refinement", () => {
  const nodes = [{ id: "A" }, { id: "B" }, { id: "C" }];
  const positions = seedPositions(
    nodes,
    [
      { from: "B", to: "A" },
      { from: "C", to: "B" },
    ],
    [{ node_ids: ["A", "B"] }, { node_ids: ["C"] }],
  );
  expect(Object.keys(positions)).toHaveLength(3);
  expect(positions.A.y).toBeLessThan(positions.B.y);
  expect(positions.B.y).toBeLessThan(positions.C.y);
  expect(positions.C.x).toBeGreaterThan(positions.B.x);
});
