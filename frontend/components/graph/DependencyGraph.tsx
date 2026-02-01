'use client';

import React, { useCallback, useEffect, useState } from 'react';
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
import { useTheme } from 'next-themes';
import { GraphNode, type GraphNodeData } from './GraphNode';
import { GraphGroupNode } from './GraphGroupNode';
import { GraphControls } from './GraphControls';
import { getAllDependencies, type Dependency } from '@/lib/api/dependencies';
import { getDocuments } from '@/lib/api/documents';
import { getApiErrorMessage } from '@/lib/api/client';
import type { DocumentListItem } from '@/types';

const NODE_WIDTH = 200;
const NODE_HEIGHT = 60;
const GROUP_PADDING = 30;
const GROUP_HEADER = 28;

const nodeTypes = { document: GraphNode, group: GraphGroupNode };

// Palette of colors for folder groups (works at low opacity in both themes)
const GROUP_COLORS = [
  '210 80% 60%',
  '160 70% 50%',
  '340 75% 55%',
  '45 90% 55%',
  '270 60% 60%',
  '190 80% 45%',
  '15 85% 55%',
  '300 50% 55%',
];

function getGroupColor(index: number, isDark: boolean): string {
  const hsl = GROUP_COLORS[index % GROUP_COLORS.length];
  return `hsl(${hsl} / ${isDark ? 0.12 : 0.08})`;
}

/** Apply dagre auto-layout to position nodes. */
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

/** Transform API data into reactflow nodes and edges with folder grouping. */
function buildGraph(
  docs: DocumentListItem[],
  deps: Dependency[],
  direction: 'TB' | 'LR',
  isDark: boolean,
): { nodes: Node[]; edges: Edge[] } {
  // Collect all document IDs referenced by dependencies
  const referencedIds = new Set<string>();
  for (const dep of deps) {
    referencedIds.add(dep.from_doc_id);
    referencedIds.add(dep.to_doc_id);
  }

  const docMap = new Map(docs.map((d) => [d.id, d]));

  // Build document nodes
  const rawNodes: Node[] = [];
  const nodeToFolder = new Map<string, string>();

  for (const id of Array.from(referencedIds)) {
    const doc = docMap.get(id);
    if (!doc) continue;
    const folder = doc.path || 'ungrouped';
    nodeToFolder.set(id, folder);
    rawNodes.push({
      id,
      type: 'document',
      position: { x: 0, y: 0 },
      data: {
        label: doc.title,
        path: doc.path,
        keywords: doc.keywords ?? [],
        direction,
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
      zIndex: 1,
      style: { strokeWidth: 1.5 },
      label: dep.link_text ?? undefined,
    }));

  // Run dagre on flat nodes first
  const laidOutNodes = layoutGraph(rawNodes, edges, direction);

  // Group nodes by folder path
  const folderToNodes = new Map<string, Node[]>();
  for (const node of laidOutNodes) {
    const folder = nodeToFolder.get(node.id) || 'ungrouped';
    if (!folderToNodes.has(folder)) folderToNodes.set(folder, []);
    folderToNodes.get(folder)!.push(node);
  }

  // Create group nodes and re-parent document nodes
  const allNodes: Node[] = [];
  let colorIndex = 0;

  // Sort folders for stable color assignment
  const sortedFolders = Array.from(folderToNodes.keys()).sort();

  for (const folder of sortedFolders) {
    const members = folderToNodes.get(folder)!;
    const groupId = `group-${folder}`;
    const color = getGroupColor(colorIndex++, isDark);

    // Compute bounding box
    const minX = Math.min(...members.map((n) => n.position.x)) - GROUP_PADDING;
    const minY = Math.min(...members.map((n) => n.position.y)) - GROUP_PADDING - GROUP_HEADER;
    const maxX = Math.max(...members.map((n) => n.position.x + NODE_WIDTH)) + GROUP_PADDING;
    const maxY = Math.max(...members.map((n) => n.position.y + NODE_HEIGHT)) + GROUP_PADDING;

    const groupWidth = maxX - minX;
    const groupHeight = maxY - minY;

    // Create group node
    allNodes.push({
      id: groupId,
      type: 'group',
      position: { x: minX, y: minY },
      data: { label: folder || 'Root', color },
      width: groupWidth,
      height: groupHeight,
      style: {
        width: groupWidth,
        height: groupHeight,
        padding: 0,
        backgroundColor: 'transparent',
        border: 'none',
      },
    });

    // Convert children to relative positions within group
    for (const member of members) {
      member.parentId = groupId;
      member.extent = 'parent' as const;
      member.position = {
        x: member.position.x - minX,
        y: member.position.y - minY,
      };
      allNodes.push(member);
    }
  }

  return { nodes: allNodes, edges };
}

function DependencyGraphInner() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
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

  const isDark = resolvedTheme === 'dark' || resolvedTheme === 'custom';

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [docsResult, depsResult] = await Promise.allSettled([
      getDocuments({ limit: 500 }),
      getAllDependencies(),
    ]);

    if (docsResult.status === 'rejected' && depsResult.status === 'rejected') {
      const msg = getApiErrorMessage(docsResult.reason);
      console.error('Graph: both API calls failed', docsResult.reason, depsResult.reason);
      setError(msg);
      setLoading(false);
      return;
    }

    const docs = docsResult.status === 'fulfilled' ? docsResult.value : [];
    const deps = depsResult.status === 'fulfilled' ? depsResult.value : [];

    if (docsResult.status === 'rejected') {
      console.error('Graph: failed to load documents', docsResult.reason);
    }
    if (depsResult.status === 'rejected') {
      console.error('Graph: failed to load dependencies', depsResult.reason);
    }

    setRawData({ docs, deps });
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Re-layout when data, direction, or theme changes
  useEffect(() => {
    if (!rawData) return;
    const { nodes: n, edges: e } = buildGraph(rawData.docs, rawData.deps, direction, isDark);
    setNodes(n);
    setEdges(e);
    setTimeout(() => fitView({ padding: 0.2 }), 50);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawData, direction, isDark]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      // Only navigate for document nodes, not group nodes
      if (node.type === 'document') {
        router.push(`/docs/${node.id}`);
      }
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
      <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground text-sm">
        <p>Failed to load dependency graph</p>
        <button
          onClick={loadData}
          className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-muted transition-colors"
        >
          Retry
        </button>
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
        colorMode={isDark ? 'dark' : 'light'}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodeDragThreshold={5}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="hsl(var(--border))" />
        <MiniMap
          nodeStrokeWidth={2}
          nodeColor="hsl(var(--primary))"
          maskColor="hsl(var(--background) / 0.6)"
          style={{ background: 'hsl(var(--muted))' }}
        />
      </ReactFlow>
    </div>
  );
}

export function DependencyGraph() {
  return (
    <ReactFlowProvider>
      <DependencyGraphInner />
    </ReactFlowProvider>
  );
}
