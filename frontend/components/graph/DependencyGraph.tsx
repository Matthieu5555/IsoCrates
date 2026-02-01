'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Node,
  type Edge,
  MiniMap,
  Background,
  BackgroundVariant,
} from '@xyflow/react';
import dagre from 'dagre';
import { useRouter } from 'next/navigation';
import { GraphNode, type GraphNodeData } from './GraphNode';
import { GraphControls } from './GraphControls';
import { getAllDependencies, type Dependency } from '@/lib/api/dependencies';
import { getDocuments } from '@/lib/api/documents';
import type { DocumentListItem } from '@/types';

// -- Constants for dagre layout --
// Node dimensions used by dagre to calculate positions.
// Changing these affects spacing between nodes in the auto-layout.
const NODE_WIDTH = 200;
const NODE_HEIGHT = 60;

const nodeTypes = { document: GraphNode };

/** Apply dagre auto-layout to position nodes as a directed acyclic graph. */
function layoutGraph(
  nodes: Node[],
  edges: Edge[],
  direction: 'TB' | 'LR',
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 80 });

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });
}

/** Transform API data into reactflow nodes and edges. */
function buildGraph(
  docs: DocumentListItem[],
  deps: Dependency[],
  direction: 'TB' | 'LR',
): { nodes: Node[]; edges: Edge[] } {
  // Collect all document IDs referenced by dependencies
  const referencedIds = new Set<string>();
  for (const dep of deps) {
    referencedIds.add(dep.from_doc_id);
    referencedIds.add(dep.to_doc_id);
  }

  const docMap = new Map(docs.map((d) => [d.id, d]));

  const rawNodes: Node[] = [];
  for (const id of Array.from(referencedIds)) {
    const doc = docMap.get(id);
    if (!doc) continue; // Skip references to deleted/non-existent documents
    rawNodes.push({
      id,
      type: 'document',
      position: { x: 0, y: 0 },
      data: {
        label: doc.title,
        path: doc.path,
        keywords: doc.keywords ?? [],
      } satisfies GraphNodeData,
    });
  }

  const nodeIds = new Set(rawNodes.map((n) => n.id));
  const edges: Edge[] = deps
    .filter((dep) => nodeIds.has(dep.from_doc_id) && nodeIds.has(dep.to_doc_id))
    .map((dep) => ({
      id: `e-${dep.id}`,
      source: dep.from_doc_id,
      target: dep.to_doc_id,
      animated: true,
      style: { stroke: 'var(--primary)', strokeWidth: 1.5 },
      label: dep.link_text ?? undefined,
    }));

  const nodes = layoutGraph(rawNodes, edges, direction);
  return { nodes, edges };
}

function DependencyGraphInner() {
  const router = useRouter();
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [direction, setDirection] = useState<'TB' | 'LR'>('TB');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rawData, setRawData] = useState<{
    docs: DocumentListItem[];
    deps: Dependency[];
  } | null>(null);

  // Fetch documents and dependencies once
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [docs, deps] = await Promise.all([
          getDocuments({ limit: 1000 }),
          getAllDependencies(),
        ]);
        if (!cancelled) {
          setRawData({ docs, deps });
        }
      } catch (err) {
        console.error('Failed to load graph data:', err);
        if (!cancelled) {
          setError('Could not load graph data. Make sure the backend is running.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // Re-layout when data or direction changes
  useEffect(() => {
    if (!rawData) return;
    const { nodes: n, edges: e } = buildGraph(rawData.docs, rawData.deps, direction);
    setNodes(n);
    setEdges(e);
    // Fit view after layout settles
    setTimeout(() => fitView({ padding: 0.2 }), 50);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawData, direction]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      router.push(`/docs/${node.id}`);
    },
    [router],
  );

  const toggleDirection = useCallback(() => {
    setDirection((d) => (d === 'TB' ? 'LR' : 'TB'));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Loading graph...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        {error}
      </div>
    );
  }

  if (!rawData || rawData.deps.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        No document dependencies found. Create wikilinks between documents to see the graph.
      </div>
    );
  }

  return (
    <div className="relative w-full h-full">
      <GraphControls
        direction={direction}
        onToggleDirection={toggleDirection}
        onZoomIn={() => zoomIn()}
        onZoomOut={() => zoomOut()}
        onFitView={() => fitView({ padding: 0.2 })}
      />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        <MiniMap
          nodeStrokeWidth={2}
          className="!bg-muted/50 !border-border"
        />
      </ReactFlow>
    </div>
  );
}

/**
 * Dependency graph visualization for document wikilinks.
 *
 * Fetches all documents and their dependency relationships, then renders
 * an interactive force-directed graph using reactflow with dagre auto-layout.
 * Clicking a node navigates to that document.
 *
 * Must be wrapped in ReactFlowProvider (handled internally here).
 */
export function DependencyGraph() {
  return (
    <ReactFlowProvider>
      <DependencyGraphInner />
    </ReactFlowProvider>
  );
}
