import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, {
  type Core,
  type ElementDefinition,
  type StylesheetStyle,
} from "cytoscape";
import { useNavigate } from "react-router";
import {
  contractAux,
  aggregateEdges,
  defaultCollapsed,
  toMermaid,
} from "../../data/graph/contract.mjs";
import { layout } from "./layout";
import { seedPositions } from "../../data/graph/seed.mjs";
import { glyphs, blueprintUrl, ErrorView } from "../../components/ui";
import type { DocumentBundle, Manifest } from "../../data/source";
import type { NodeSummary, NodeRef, Edge } from "../../data/types";
import { t } from "../../i18n/t";
type GraphNode = (NodeSummary | NodeRef) & { chapterSummary?: boolean };
export const styles: StylesheetStyle[] = [
  {
    selector: "node",
    style: {
      shape: "roundrectangle",
      width: 204,
      height: 70,
      "background-color": "#ffffff",
      "border-width": 2,
      "border-color": "#63776a",
      label: "data(label)",
      color: "#183426",
      "font-family": "system-ui",
      "font-size": 12,
      "text-wrap": "wrap",
      "text-max-width": "182px",
      "text-valign": "center",
      "text-halign": "center",
      "min-zoomed-font-size": 8,
    },
  },
  {
    selector: 'node[headline = "statement-complete"]',
    style: { "background-color": "#d6efdc", "border-color": "#3f7850" },
  },
  {
    selector: 'node[headline = "proof-complete"]',
    style: {
      "background-color": "#247347",
      color: "#ffffff",
      "border-color": "#164d2e",
    },
  },
  {
    selector: 'node[headline = "error"]',
    style: {
      "background-color": "#ffe0dc",
      "border-color": "#b02e22",
      color: "#7d2018",
    },
  },
  {
    selector: 'node[headline = "none"]',
    style: { "background-color": "#d5dcd7" },
  },
  {
    selector: 'node[status = "pruned"]',
    style: { "background-color": "#d5dcd7", "background-opacity": 0.5 },
  },
  {
    selector: 'node[status = "proved-modulo-citations"]',
    style: { "border-style": "dashed", "border-width": 3 },
  },
  {
    selector: 'node[status = "proved-pending-deps"]',
    style: {
      "border-style": "dashed",
      "border-width": 3,
      "background-image": `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><path d="M0 8L8 0" stroke="#597d60" stroke-opacity=".25"/></svg>',
      )}`,
      "background-repeat": "repeat",
      "background-width": "8px",
      "background-height": "8px",
    },
  },
  {
    selector: 'node[status = "proved-with-axioms"]',
    style: { "border-color": "#b77b00", "border-width": 4 },
  },
  {
    selector: 'node[fidelity = "foundation"]',
    style: { "border-color": "#3c4650", "border-width": 3 },
  },
  {
    selector: 'node[fidelity = "deviates"]',
    style: { "border-color": "#bc5c00", "border-width": 3 },
  },
  {
    selector: "node[raised = 1]",
    style: {
      "border-color": "#8052a3",
      "border-style": "dashed",
      "border-width": 3,
    },
  },
  { selector: "node[aux = 1]", style: { width: 168, height: 58 } },
  { selector: "node[bridge = 1]", style: { shape: "diamond", height: 104 } },
  {
    selector: "node[cited = 1]",
    style: { shape: "hexagon", "border-style": "dashed" },
  },
  {
    selector: "node[external = 1]",
    style: { "border-style": "dashed", "background-color": "#edf2ef" },
  },
  {
    selector: ":parent",
    style: {
      "background-color": "#e8efe9",
      "background-opacity": 0.35,
      "border-width": 1,
      "border-color": "#c2d0c5",
      label: "data(label)",
      "text-valign": "top",
      "font-weight": "bold",
      padding: "28px",
      shape: "roundrectangle",
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.8,
      "line-color": "#778a7e",
      "target-arrow-color": "#778a7e",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.9,
      label: "data(viaLabel)",
      "font-size": 11,
      color: "#385543",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.9,
      "text-background-padding": "3px",
    },
  },
  { selector: "edge[verified = 0]", style: { "line-style": "dashed" } },
  {
    selector: "edge[declared = 0]",
    style: { "line-color": "#c6691b", "target-arrow-color": "#c6691b" },
  },
  {
    selector: 'edge[kind = "proof"]',
    style: { "target-arrow-fill": "hollow" },
  },
  {
    selector: ".focus",
    style: {
      "underlay-color": "#268651",
      "underlay-opacity": 0.2,
      "underlay-padding": 10,
    },
  },
  { selector: ".neighbor", style: { "border-width": 4 } },
];
export function Blueprint({
  bundle,
  manifest,
  selected,
  chapter,
  filter,
  headline,
  expandAux,
  collapsedChapters,
  onToggleChapter,
  direction,
  edgeMode,
}: {
  bundle: DocumentBundle;
  manifest: Manifest;
  selected?: string;
  chapter: string;
  filter: string;
  headline: string;
  expandAux: boolean;
  collapsedChapters: Set<string>;
  onToggleChapter: (chapter: string) => void;
  direction: string;
  edgeMode: string;
}) {
  const container = useRef<HTMLDivElement>(null),
    cy = useRef<Core | null>(null),
    navigate = useNavigate();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [tooltip, setTooltip] = useState(""),
    [context, setContext] = useState<NodeSummary>(),
    [notice, setNotice] = useState("");
  const auxStorageKey = `homalg:aux:${bundle.document.doc_key}`;
  const [expandedParents, setExpandedParents] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(sessionStorage.getItem(auxStorageKey) || "[]"));
    } catch {
      return new Set();
    }
  });
  const nodeById = useMemo(
    () => new Map(bundle.nodes.map((node) => [node.id, node])),
    [bundle],
  );
  const auxParents = useMemo(
    () =>
      new Set(
        bundle.nodes
          .filter((node) => node.is_aux && node.aux_kind !== "bridge")
          .map((node) => node.aux_parent),
      ),
    [bundle],
  );
  const toggleAux = (id: string) =>
    setExpandedParents((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        sessionStorage.setItem(auxStorageKey, JSON.stringify([...next]));
      } catch {
        /* Storage is optional. */
      }
      return next;
    });
  const entry = manifest.documents.find(
    (doc) => doc.doc_key === bundle.document.doc_key,
  )!;
  const graph = useMemo(() => {
    const computedAt = performance.now();
    const collapsed: Set<string> = expandAux
      ? new Set()
      : defaultCollapsed(bundle.nodes);
    for (const node of bundle.nodes) {
      if (node.aux_parent && expandedParents.has(node.aux_parent))
        collapsed.delete(node.id);
    }
    if (selected) {
      let node = nodeById.get(selected);
      while (node) {
        collapsed.delete(node.id);
        node = nodeById.get(node.aux_parent || "");
      }
    }
    const edges = contractAux(
      bundle.nodes,
      bundle.edges,
      collapsed,
    ) as (Edge & { via?: string[] })[];
    let nodes: GraphNode[] = bundle.nodes.filter(
      (node) => !collapsed.has(node.id),
    );
    const chapterOf = new Map(
      bundle.chapters.flatMap((item) =>
        item.node_ids.map((id) => [id, item.chapter] as const),
      ),
    );
    const replaced = new Map<string, string>();
    for (const item of bundle.chapters) {
      if (
        collapsedChapters.has(item.chapter) &&
        !item.node_ids.includes(selected || "")
      ) {
        const members = nodes.filter(
          (node) => chapterOf.get(node.id) === item.chapter,
        );
        if (members.length) {
          const id = `chapter:${item.chapter}`;
          members.forEach((node) => replaced.set(node.id, id));
          nodes = nodes.filter(
            (node) => chapterOf.get(node.id) !== item.chapter,
          );
          nodes.push({
            ...members[0],
            id,
            label: `${item.chapter} · ${item.title || ""}\n${t("doc.more", { count: members.length })}`,
            chapterSummary: true,
          });
        }
      }
    }
    nodes = nodes.filter(
      (node) =>
        node.id === selected ||
        ((!chapter ||
          chapterOf.get(node.id) === chapter ||
          node.id === `chapter:${chapter}`) &&
          (!filter ||
            `${node.id} ${node.label} ${"title" in node ? node.title : ""}`
              .toLowerCase()
              .includes(filter.toLowerCase())) &&
          (!headline || node.headline === headline)),
    );
    const ids = new Set(nodes.map((node) => node.id));
    const visibleEdges = aggregateEdges(
      edges
        .map((edge) => ({
          ...edge,
          from: replaced.get(edge.from) || edge.from,
          to: replaced.get(edge.to) || edge.to,
        }))
        .filter(
          (edge) =>
            edge.from !== edge.to &&
            ids.has(edge.from) &&
            (edgeMode !== "verified" || edge.verified) &&
            (edgeMode !== "declared" || edge.declared),
        ),
    ) as (Edge & { via?: string[]; aggregate_count: number })[];
    const externals = bundle.external_nodes.filter((node) =>
      visibleEdges.some((edge) => edge.to === node.id),
    );
    nodes.push(...externals);
    externals.forEach((node) => ids.add(node.id));
    return {
      nodes,
      edges: visibleEdges.filter((edge) => ids.has(edge.to)),
      chapterOf,
      collapsed,
      replaced,
      computedAt,
      computeMs: performance.now() - computedAt,
    };
  }, [
    bundle,
    nodeById,
    expandedParents,
    selected,
    chapter,
    filter,
    headline,
    expandAux,
    collapsedChapters,
    edgeMode,
  ]);
  useEffect(() => {
    let cancelled = false;
    setError(undefined);
    const apply = async () => {
      const applyAt = performance.now();
      if (!container.current) return;
      setBusy(true);
      const defaults =
        !chapter &&
        !filter &&
        !headline &&
        !expandAux &&
        !expandedParents.size &&
        (!collapsedChapters.size ||
          collapsedChapters.size === bundle.chapters.length) &&
        direction === "DOWN" &&
        edgeMode === "all" &&
        !selected?.includes(".Aux_");
      const key = `${entry.doc_key}:${entry.graph_hash}:${direction}:${graph.nodes.map((node) => node.id).join(",")}:${edgeMode}`;
      const chapters = bundle.chapters.map((item) => ({
        ...item,
        node_ids: [...item.node_ids, `chapter:${item.chapter}`],
      }));
      const precomputed =
        bundle.layout?.view === "aux-collapsed"
          ? bundle.layout.nodes
          : undefined;
      const projected = precomputed ? { ...precomputed } : undefined;
      if (projected && collapsedChapters.size)
        for (const item of bundle.chapters) {
          const points = item.node_ids
            .map((id) => projected[id])
            .filter(Boolean);
          if (points.length)
            projected[`chapter:${item.chapter}`] = {
              x:
                points.reduce((sum, point) => sum + point.x, 0) / points.length,
              y:
                points.reduce((sum, point) => sum + point.y, 0) / points.length,
            };
        }
      const refinement =
        defaults && projected
          ? undefined
          : layout(graph.nodes, graph.edges, chapters, key, direction);
      const positions =
        defaults && projected
          ? projected
          : seedPositions(graph.nodes, graph.edges, chapters, direction);
      if (cancelled) return;
      const elements: ElementDefinition[] = [];
      for (const item of bundle.chapters)
        if (
          graph.nodes.some(
            (node) =>
              graph.chapterOf.get(node.id) === item.chapter &&
              !node.chapterSummary,
          )
        )
          elements.push({
            data: {
              id: `group:${item.chapter}`,
              label: `${item.chapter} · ${item.title || ""}`,
              chapter: item.chapter,
            },
          });
      const auxCounts = new Map<string, number>();
      for (const item of bundle.nodes)
        if (item.aux_parent && graph.collapsed.has(item.id))
          auxCounts.set(
            item.aux_parent,
            (auxCounts.get(item.aux_parent) || 0) + 1,
          );
      for (const node of graph.nodes) {
        const local = nodeById.get(node.id),
          auxCount = auxCounts.get(node.id) || 0;
        elements.push({
          data: {
            id: node.id,
            auxCount,
            label: `${local?.needs_repair ? "⚒ " : ""}${glyphs[node.status]} ${node.label}${local?.title ? `\n${local.title}` : ""}${auxCount ? `\n${t("doc.auxCount", { count: auxCount })}` : ""}`,
            headline: node.headline || "none",
            status: node.status,
            fidelity: local?.fidelity_status,
            raised: local?.disputed && local.headline !== "error" ? 1 : 0,
            aux: local?.is_aux ? 1 : 0,
            bridge: local?.aux_kind === "bridge" ? 1 : 0,
            cited: local?.local_id.startsWith("Cited_") ? 1 : 0,
            external: !local && !node.chapterSummary ? 1 : 0,
            parent:
              !node.chapterSummary && graph.chapterOf.has(node.id)
                ? `group:${graph.chapterOf.get(node.id)}`
                : undefined,
            chapterSummary: node.chapterSummary ? 1 : 0,
          },
          position: positions[node.id] || { x: 0, y: 0 },
        });
      }
      graph.edges.forEach((edge, i) =>
        elements.push({
          data: {
            id: `edge:${i}`,
            source: edge.to,
            target: edge.from,
            kind: edge.kind,
            declared: edge.declared ? 1 : 0,
            verified: edge.verified ? 1 : 0,
            viaLabel:
              edge.aggregate_count > 1
                ? t("doc.edgeCount", { count: edge.aggregate_count })
                : edge.via?.length
                  ? `+${edge.via.length}`
                  : "",
            via: edge.via?.join(", ") || "",
          },
        }),
      );
      cy.current?.destroy();
      container.current.dataset.ready = "false";
      const constructAt = performance.now();
      const instance = cytoscape({
        container: container.current,
        elements,
        style: styles,
        layout: { name: "preset" },
        hideEdgesOnViewport: graph.nodes.length > 1500,
        textureOnViewport: graph.nodes.length > 1500,
        wheelSensitivity: 0.2,
        minZoom: graph.nodes.length > 500 ? 0.002 : 0.12,
        maxZoom: 3,
      });
      const constructMs = performance.now() - constructAt;
      cy.current = instance;
      instance.one("render", () => {
        if (!cancelled && container.current) {
          container.current.dataset.ready = "true";
          container.current.dataset.readyAt = String(performance.now());
          container.current.dataset.visibleNodes = String(graph.nodes.length);
          container.current.dataset.profile = JSON.stringify({
            graphAt: graph.computedAt,
            graphMs: graph.computeMs,
            applyAt,
            constructAt,
            constructMs,
            visibleEdges: graph.edges.length,
            precomputed: !!(defaults && projected),
          });
        }
      });
      instance.on("tap", "node", (event) => {
        const node = event.target;
        if (node.isParent()) onToggleChapter(node.data("chapter"));
        else if (node.data("chapterSummary"))
          onToggleChapter(node.id().slice(8));
        else {
          if (node.data("auxCount")) toggleAux(node.id());
          navigate(blueprintUrl(node.id()));
        }
      });
      instance.on("dbltap", "node", (event) => {
        const node = event.target;
        instance.elements().removeClass("neighbor");
        node.closedNeighborhood().addClass("neighbor");
        instance.fit(node.closedNeighborhood(), 70);
      });
      instance.on("mouseover", "node", (event) => {
        const node = nodeById.get(event.target.id());
        setTooltip(node?.statement_first_line || event.target.data("label"));
      });
      instance.on("mouseover", "edge", (event) =>
        setTooltip(event.target.data("via")),
      );
      instance.on("mouseout", () => setTooltip(""));
      instance.on("cxttap", "node", (event) =>
        setContext(nodeById.get(event.target.id())),
      );
      if (selected) {
        const node = instance.getElementById(selected);
        if (node.length) {
          node.addClass("focus");
          if (matchMedia("(prefers-reduced-motion: reduce)").matches)
            instance.fit(node.closedNeighborhood(), 80);
          else
            instance.animate({
              fit: { eles: node.closedNeighborhood(), padding: 80 },
              duration: 250,
            });
          setTimeout(() => {
            if (!instance.destroyed()) node.removeClass("focus");
          }, 2000);
        }
      } else instance.fit(undefined, 35);
      if (refinement)
        void refinement
          .then((refined) => {
            if (cancelled || instance.destroyed()) return;
            instance.batch(() => {
              for (const node of graph.nodes)
                if (refined[node.id])
                  instance.getElementById(node.id).position(refined[node.id]);
            });
            const focus = selected
              ? instance.getElementById(selected)
              : undefined;
            instance.fit(
              focus?.length ? focus.closedNeighborhood() : undefined,
              35,
            );
            setBusy(false);
          })
          .catch((reason) => {
            if (!cancelled) {
              setError(reason);
              setBusy(false);
            }
          });
      else setBusy(false);
    };
    void apply().catch((reason) => {
      if (!cancelled) {
        setError(reason);
        setBusy(false);
      }
    });
    return () => {
      cancelled = true;
      cy.current?.destroy();
      cy.current = null;
    };
  }, [
    bundle,
    graph,
    nodeById,
    expandedParents,
    entry,
    chapter,
    filter,
    headline,
    expandAux,
    collapsedChapters,
    direction,
    edgeMode,
    selected,
    navigate,
    onToggleChapter,
  ]);
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(t("doc.copyDone"));
    } catch {
      setNotice(t("doc.copyFailed"));
    }
  };
  return (
    <div className="blueprint">
      <div className="graph-actions">
        {selected && auxParents.has(selected) && !expandAux && (
          <button onClick={() => toggleAux(selected)}>
            {expandedParents.has(selected)
              ? t("doc.collapseParentAux")
              : t("doc.expandParentAux")}
          </button>
        )}
        <button
          onClick={() => {
            if (!cy.current) return;
            const link = document.createElement("a");
            link.href = cy.current.png({ full: true, scale: 2, bg: "#f6f8f6" });
            link.download = `${entry.doc_key}.png`;
            link.click();
          }}
        >
          {t("doc.exportPng")}
        </button>
        <button onClick={() => void copy(toMermaid(graph.nodes, graph.edges))}>
          {t("doc.exportMermaid")}
        </button>
      </div>
      {!!error && <ErrorView error={error} />}
      <p id="graph-help" className="sr-only">
        {t("doc.graphHelp")}
      </p>
      <div
        ref={container}
        className="graph-canvas"
        role="img"
        tabIndex={0}
        aria-label={t("doc.graphSummary", {
          doc: entry.doc_key,
          count: graph.nodes.length,
          proved: entry.headline_counts["proof-complete"],
          chapters: bundle.chapters.length,
        })}
        aria-describedby="graph-help"
        onKeyDown={(event) => {
          if (!event.key.startsWith("Arrow") || !cy.current) return;
          event.preventDefault();
          const current = selected
            ? cy.current.getElementById(selected)
            : cy.current.nodes().not(":parent").first();
          const neighbors = current.neighborhood().nodes().not(":parent");
          const target = neighbors.length
            ? neighbors[
                event.key === "ArrowUp" || event.key === "ArrowLeft"
                  ? 0
                  : neighbors.length - 1
              ]
            : current;
          if (target) navigate(blueprintUrl(target.id()));
        }}
      />
      {busy && (
        <div className="layout-status" role="status">
          {t("doc.layout")}
        </div>
      )}
      {tooltip && (
        <div className="graph-tooltip" role="tooltip">
          {tooltip}
        </div>
      )}
      {notice && (
        <p className="graph-notice" role="status">
          {notice}
        </p>
      )}
      {context && (
        <div className="graph-context" role="menu" aria-label={t("doc.menu")}>
          <button
            role="menuitem"
            onClick={() => {
              void copy(context.id);
              setContext(undefined);
            }}
          >
            {t("doc.copyId")}
          </button>
          <button
            role="menuitem"
            onClick={() => {
              void copy(context.decl_names.join("\n"));
              setContext(undefined);
            }}
          >
            {t("doc.copyLean")}
          </button>
          <a
            role="menuitem"
            href={`${manifest.repo_url}/blob/${manifest.commit}/HomAlg/${context.doc}/${context.local_id}.lean`}
            target="_blank"
            rel="noreferrer"
          >
            {t("node.github")}
          </a>
          <button
            role="menuitem"
            onClick={() =>
              navigate(`/search?deps=${context.id}&dir=up&depth=2`)
            }
          >
            {t("doc.transitive")}
          </button>
          <button role="menuitem" onClick={() => setContext(undefined)}>
            {t("node.close")}
          </button>
        </div>
      )}
    </div>
  );
}
