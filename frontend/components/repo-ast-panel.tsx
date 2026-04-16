"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiBase } from "@/lib/api-base";
import { createClient } from "@/lib/supabase/client";
import { isValidUuid } from "@/lib/uuid";

type AstNode = {
  id: string;
  kind: string;
  ast_type?: string;
  name?: string;
  file?: string;
  line?: number;
  code_snippet?: string;
};

type AstEdge = {
  source: string;
  target: string;
  type: string;
};

type AstGraph = {
  nodes?: AstNode[];
  edges?: AstEdge[];
  file_count?: number;
  node_count?: number;
  edge_count?: number;
};

export type AstSnapshot = {
  branch?: string;
  commit_sha?: string;
  ast_graph_json?: AstGraph;
};

export function RepoAstPanel({
  repoId,
  initialSnapshot,
  initialError,
}: {
  repoId: string;
  initialSnapshot: AstSnapshot | null;
  initialError: string | null;
}) {
  const [snapshot, setSnapshot] = useState<AstSnapshot | null>(initialSnapshot);
  const [branch, setBranch] = useState(initialSnapshot?.branch ?? "");
  const [message, setMessage] = useState<string | null>(initialError);
  const [isBuilding, setIsBuilding] = useState(false);
  const [view, setView] = useState<"tree" | "graph">("graph");
  const canBuild = isValidUuid(repoId);

  async function handleBuild() {
    setIsBuilding(true);
    setMessage(null);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const headers = new Headers({
        Accept: "application/json",
        "Content-Type": "application/json",
      });
      if (session?.access_token) {
        headers.set("Authorization", `Bearer ${session.access_token}`);
      }
      const response = await fetch(`${apiBase()}/v1/repos/${repoId}/ast/build`, {
        method: "POST",
        headers,
        body: JSON.stringify(branch.trim() ? { branch: branch.trim() } : {}),
      });
      const payload = (await response.json()) as {
        detail?: string;
        snapshot?: AstSnapshot;
      };
      if (!response.ok) {
        setMessage(payload.detail ?? `Request failed (${response.status})`);
        return;
      }
      setSnapshot(payload.snapshot ?? null);
      setMessage("AST snapshot generated.");
      if (payload.snapshot?.branch) {
        setBranch(payload.snapshot.branch);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to build AST snapshot");
    } finally {
      setIsBuilding(false);
    }
  }

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="text-base">AST Explorer</CardTitle>
        <CardDescription>
          Generate and browse the full AST tree for this repository.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Input
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
            placeholder="Leave blank to use the repo default branch"
          />
          <Button onClick={handleBuild} disabled={isBuilding || !canBuild}>
            {isBuilding ? "Building..." : "Build AST"}
          </Button>
        </div>

        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

        {snapshot?.ast_graph_json ? (
          <>
            <div className="rounded-lg border border-border bg-muted/20 p-3 text-xs">
              <p>Branch: {snapshot.branch ?? "unknown"}</p>
              <p>Commit: <span className="font-mono">{snapshot.commit_sha ?? "unknown"}</span></p>
              <p>
                Files: {snapshot.ast_graph_json.file_count ?? 0} | Nodes:{" "}
                {snapshot.ast_graph_json.node_count ?? 0} | Edges:{" "}
                {snapshot.ast_graph_json.edge_count ?? 0}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant={view === "graph" ? "secondary" : "outline"}
                size="sm"
                onClick={() => setView("graph")}
              >
                Graph
              </Button>
              <Button
                variant={view === "tree" ? "secondary" : "outline"}
                size="sm"
                onClick={() => setView("tree")}
              >
                Tree
              </Button>
            </div>
            {view === "graph" ? (
              <AstGraphView graph={snapshot.ast_graph_json} />
            ) : (
              <AstTree graph={snapshot.ast_graph_json} />
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No AST snapshot yet.</p>
        )}
      </CardContent>
    </Card>
  );
}

function AstTree({ graph }: { graph: AstGraph }) {
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const children = new Map<string, string[]>();
  const childIds = new Set<string>();

  for (const edge of edges) {
    if (edge.type !== "ast_child") continue;
    const list = children.get(edge.source) ?? [];
    list.push(edge.target);
    children.set(edge.source, list);
    childIds.add(edge.target);
  }

  const roots = nodes
    .filter((node) => node.kind === "file" || !childIds.has(node.id))
    .sort((a, b) => (a.file ?? a.name ?? "").localeCompare(b.file ?? b.name ?? ""));

  return (
    <div className="max-h-[48rem] overflow-auto rounded-lg border border-border bg-muted/10 p-3 text-xs">
      <div className="space-y-1">
        {roots.map((root) => (
          <AstTreeNode
            key={root.id}
            nodeId={root.id}
            nodeMap={nodeMap}
            children={children}
            depth={0}
          />
        ))}
      </div>
    </div>
  );
}

function AstGraphView({ graph }: { graph: AstGraph }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const elements = useMemo(() => {
    const nodes = (graph.nodes ?? []).map((node) => ({
      data: {
        id: node.id,
        label: formatNodeLabel(node),
        kind: node.kind,
        astType: node.ast_type ?? node.kind,
      },
    }));
    const edges = (graph.edges ?? []).map((edge, index) => ({
      data: {
        id: `${edge.source}->${edge.target}:${edge.type}:${index}`,
        source: edge.source,
        target: edge.target,
        label: edge.type,
        edgeType: edge.type,
      },
    }));
    return [...nodes, ...edges];
  }, [graph.edges, graph.nodes]);

  useEffect(() => {
    let mounted = true;
    let cytoscapeInstance: any = null;

    async function mountGraph() {
      if (!containerRef.current) return;
      try {
        const module = await import("cytoscape");
        if (!mounted || !containerRef.current) return;
        const cytoscape = module.default;
        cytoscapeInstance = cytoscape({
          container: containerRef.current,
          elements,
          layout: {
            name: "breadthfirst",
            directed: true,
            spacingFactor: 1.2,
            padding: 24,
          },
          wheelSensitivity: 0.2,
          style: [
            {
              selector: "node",
              style: {
                "background-color": "#8fb7ff",
                label: "data(label)",
                color: "#e8eefc",
                "font-size": 9,
                "text-wrap": "wrap",
                "text-max-width": 110,
                "text-valign": "center",
                "text-halign": "center",
                width: 22,
                height: 22,
                "border-width": 1,
                "border-color": "#d7e3ff",
              },
            },
            {
              selector: 'node[kind = "file"]',
              style: {
                "background-color": "#2f6fed",
                shape: "round-rectangle",
                width: 44,
                height: 26,
              },
            },
            {
              selector: 'node[kind = "function"]',
              style: {
                "background-color": "#1fa971",
              },
            },
            {
              selector: 'node[kind = "import"]',
              style: {
                "background-color": "#f59e0b",
                shape: "diamond",
              },
            },
            {
              selector: "edge",
              style: {
                width: 1.5,
                "line-color": "#7182aa",
                "target-arrow-color": "#7182aa",
                "target-arrow-shape": "triangle",
                "curve-style": "bezier",
                opacity: 0.75,
              },
            },
            {
              selector: 'edge[edgeType = "ast_child"]',
              style: {
                width: 1.2,
              },
            },
          ],
        });
        cytoscapeInstance.on("tap", "node", (event: { target: { id: () => string } }) => {
          const nodeId = event.target.id();
          const matchedNode = (graph.nodes ?? []).find((node) => node.id === nodeId);
          if (matchedNode) {
            setGraphError(
              matchedNode.code_snippet
                ? `${formatNodeLabel(matchedNode)}: ${matchedNode.code_snippet}`
                : formatNodeLabel(matchedNode),
            );
          }
        });
        setGraphError(null);
      } catch (error) {
        setGraphError(
          error instanceof Error ? error.message : "Failed to load Cytoscape graph view.",
        );
      }
    }

    mountGraph();
    return () => {
      mounted = false;
      if (cytoscapeInstance) {
        cytoscapeInstance.destroy();
      }
    };
  }, [elements, graph.nodes]);

  return (
    <div className="space-y-3">
      <div
        ref={containerRef}
        className="h-[38rem] rounded-lg border border-border bg-[#0d1322]"
      />
      <p className="text-xs text-muted-foreground">
        Click a node to inspect its label or snippet.
      </p>
      {graphError ? (
        <pre className="whitespace-pre-wrap rounded-lg border border-border bg-muted/20 p-3 text-xs text-muted-foreground">
          {graphError}
        </pre>
      ) : null}
    </div>
  );
}

function formatNodeLabel(node: AstNode): string {
  const name = node.name || node.ast_type || node.kind;
  const line = node.line ? `L${node.line}` : "";
  return [name, line].filter(Boolean).join(" ");
}

function AstTreeNode({
  nodeId,
  nodeMap,
  children,
  depth,
}: {
  nodeId: string;
  nodeMap: Map<string, AstNode>;
  children: Map<string, string[]>;
  depth: number;
}) {
  const node = nodeMap.get(nodeId);
  if (!node) return null;
  const childIds = children.get(nodeId) ?? [];
  const label = [
    node.name || node.ast_type || node.kind,
    node.kind !== "file" && node.ast_type && node.ast_type !== node.kind ? `(${node.ast_type})` : "",
    node.line ? `L${node.line}` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div style={{ marginLeft: depth * 12 }}>
      <details open={depth < 2}>
        <summary className="cursor-pointer select-none py-1 font-mono">{label}</summary>
        {node.code_snippet ? (
          <pre className="mb-2 whitespace-pre-wrap rounded bg-background/70 p-2 text-[11px] text-muted-foreground">
            {node.code_snippet}
          </pre>
        ) : null}
        <div className="space-y-1">
          {childIds.map((childId) => (
            <AstTreeNode
              key={childId}
              nodeId={childId}
              nodeMap={nodeMap}
              children={children}
              depth={depth + 1}
            />
          ))}
        </div>
      </details>
    </div>
  );
}
