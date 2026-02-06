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
  Background,
  BackgroundVariant,
} from '@xyflow/react';
import { useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import { GraphNode } from './GraphNode';
import { GraphGroupNode } from './GraphGroupNode';
import { GraphControls } from './GraphControls';
import { GraphNodeContextMenu } from './GraphNodeContextMenu';
import { buildGraph } from './buildGraph';
import { getAllDependencies, type Dependency } from '@/lib/api/dependencies';
import { getDocuments } from '@/lib/api/documents';
import { getApiErrorMessage } from '@/lib/api/client';
import type { DocumentListItem } from '@/types';

import { DEFAULT_NODE_LIMIT } from '@/lib/config/constants';

// --- Component-level constants ---
const DEFAULT_EDGE_LIMIT = 50;    // Max edges shown before "Show All" toggle appears.
const FIT_VIEW_PADDING = 0.2;     // Fraction of viewport kept as margin when fitting view.
const MIN_ZOOM = 0.1;             // Minimum zoom level (10%). Prevents nodes from disappearing.
const MAX_ZOOM = 2;               // Maximum zoom level (200%). Prevents pixelation.
const SNAP_GRID: [number, number] = [25, 25]; // Pixels. Grid snapping distance for node positions.
const BG_DOT_GAP = 32;            // Pixels between background dots.
const GRAPH_DOC_FETCH_LIMIT = 500; // Max documents fetched for the graph. API max is 500.

const nodeTypes = { document: GraphNode, group: GraphGroupNode };

function DependencyGraphInner() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [direction, setDirection] = useState<'TB' | 'LR'>('TB');
  const [pathFilter, setPathFilter] = useState('');
  const [showAllNodes, setShowAllNodes] = useState(false);
  const [showAllEdges, setShowAllEdges] = useState(false);
  const [totalNodeCount, setTotalNodeCount] = useState(0);
  const [totalEdgeCount, setTotalEdgeCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rawData, setRawData] = useState<{
    docs: DocumentListItem[];
    deps: Dependency[];
  } | null>(null);

  // Focus state for highlighting node relationships
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    nodeId: string;
  } | null>(null);

  const isDark = resolvedTheme === 'dark' || resolvedTheme === 'custom';

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [docsResult, depsResult] = await Promise.allSettled([
      getDocuments({ limit: GRAPH_DOC_FETCH_LIMIT }),
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
    const nodeLimit = showAllNodes ? null : DEFAULT_NODE_LIMIT;
    const { nodes: n, edges: e, totalNodeCount: total } = buildGraph(
      rawData.docs, rawData.deps, direction, isDark, pathFilter, nodeLimit
    );
    setNodes(n);
    setEdges(e);
    setTotalNodeCount(total);
    setTotalEdgeCount(e.length);
    // Brief delay allows React to render nodes before fitting the viewport.
    setTimeout(() => fitView({ padding: FIT_VIEW_PADDING }), 50);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawData, direction, isDark, pathFilter, showAllNodes]);

  // Clear focus when data changes
  useEffect(() => {
    setFocusedNodeId(null);
    setContextMenu(null);
  }, [rawData, direction, pathFilter]);

  // Compute connected node IDs for focus highlighting
  const connectedNodeIds = useMemo(() => {
    if (!focusedNodeId) return new Set<string>();
    const connected = new Set<string>([focusedNodeId]);
    for (const edge of edges) {
      if (edge.source === focusedNodeId) connected.add(edge.target);
      if (edge.target === focusedNodeId) connected.add(edge.source);
    }
    return connected;
  }, [focusedNodeId, edges]);

  // Compute limited edges - keep most connected nodes' edges + focused node edges
  const limitedEdges = useMemo(() => {
    if (showAllEdges || edges.length <= DEFAULT_EDGE_LIMIT) {
      return edges;
    }

    // Count edges per node to find most connected
    const nodeEdgeCount = new Map<string, number>();
    for (const edge of edges) {
      nodeEdgeCount.set(edge.source, (nodeEdgeCount.get(edge.source) || 0) + 1);
      nodeEdgeCount.set(edge.target, (nodeEdgeCount.get(edge.target) || 0) + 1);
    }

    // Rank nodes by edge count
    const rankedNodes = Array.from(nodeEdgeCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([id]) => id);

    // Find minimum number of top nodes needed to get ~DEFAULT_EDGE_LIMIT edges
    const topNodes = new Set<string>();
    let edgeCount = 0;
    for (const nodeId of rankedNodes) {
      topNodes.add(nodeId);
      // Count edges where both ends are in topNodes
      edgeCount = edges.filter(
        (e) => topNodes.has(e.source) && topNodes.has(e.target)
      ).length;
      if (edgeCount >= DEFAULT_EDGE_LIMIT) break;
    }

    // Always include focused node
    if (focusedNodeId) {
      topNodes.add(focusedNodeId);
    }

    // Filter edges: keep if both ends in topNodes OR connected to focused node
    return edges.filter((edge) => {
      const inTopNodes = topNodes.has(edge.source) && topNodes.has(edge.target);
      const connectedToFocused = focusedNodeId &&
        (edge.source === focusedNodeId || edge.target === focusedNodeId);
      return inTopNodes || connectedToFocused;
    });
  }, [edges, showAllEdges, focusedNodeId]);

  // Apply focus styling to nodes
  const styledNodes = useMemo(() => {
    if (!focusedNodeId) return nodes;
    return nodes.map((node) => {
      if (node.type === 'group') {
        // Check if any child document is connected
        const hasConnectedChild = nodes.some(
          (n) => n.parentId === node.id && connectedNodeIds.has(n.id)
        );
        return {
          ...node,
          data: { ...node.data, isDimmed: !hasConnectedChild },
        };
      }
      const isConnected = connectedNodeIds.has(node.id);
      return {
        ...node,
        data: {
          ...node.data,
          isFocused: node.id === focusedNodeId,
          isDimmed: !isConnected,
        },
      };
    });
  }, [nodes, focusedNodeId, connectedNodeIds]);

  // Apply focus styling to edges (using limitedEdges)
  const styledEdges = useMemo(() => {
    if (!focusedNodeId) return limitedEdges;
    return limitedEdges.map((edge) => {
      const isConnected = edge.source === focusedNodeId || edge.target === focusedNodeId;
      return {
        ...edge,
        style: {
          ...edge.style,
          opacity: isConnected ? 1 : 0.15,
          strokeWidth: isConnected ? 1.5 : 1,
        },
      };
    });
  }, [limitedEdges, focusedNodeId]);

  // Toggle focus on node click (no longer navigates directly)
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (node.type === 'document') {
        setFocusedNodeId((current) => (current === node.id ? null : node.id));
      }
      setContextMenu(null);
    },
    [],
  );

  // Show context menu on right-click
  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      if (node.type !== 'document') return;
      event.preventDefault();
      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        nodeId: node.id,
      });
    },
    [],
  );

  // Clear focus when clicking on empty pane
  const handlePaneClick = useCallback(() => {
    setFocusedNodeId(null);
    setContextMenu(null);
  }, []);

  // Context menu actions
  const handleOpenDocument = useCallback(() => {
    if (contextMenu) {
      router.push(`/docs/${contextMenu.nodeId}`);
      setContextMenu(null);
    }
  }, [contextMenu, router]);

  const handleToggleFocus = useCallback(() => {
    if (contextMenu) {
      setFocusedNodeId((current) =>
        current === contextMenu.nodeId ? null : contextMenu.nodeId
      );
      setContextMenu(null);
    }
  }, [contextMenu]);

  const handleCloseContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const toggleDirection = useCallback(() => {
    setDirection((d) => (d === 'TB' ? 'LR' : 'TB'));
  }, []);

  const toggleShowAllNodes = useCallback(() => {
    setShowAllNodes((s) => !s);
  }, []);

  const toggleShowAllEdges = useCallback(() => {
    setShowAllEdges((s) => !s);
  }, []);

  // Count document nodes (exclude group nodes)
  const documentNodeCount = useMemo(() => {
    return nodes.filter((n) => n.type === 'document').length;
  }, [nodes]);

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
        pathFilter={pathFilter}
        showAllNodes={showAllNodes}
        nodeCount={documentNodeCount}
        totalNodes={totalNodeCount}
        showAllEdges={showAllEdges}
        edgeCount={limitedEdges.length}
        totalEdges={totalEdgeCount}
        onToggleDirection={toggleDirection}
        onZoomIn={() => zoomIn()}
        onZoomOut={() => zoomOut()}
        onFitView={() => fitView({ padding: FIT_VIEW_PADDING })}
        onPathFilterChange={setPathFilter}
        onToggleShowAllNodes={toggleShowAllNodes}
        onToggleShowAllEdges={toggleShowAllEdges}
      />
      <ReactFlow
        nodes={styledNodes}
        edges={styledEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeContextMenu={handleNodeContextMenu}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        colorMode={isDark ? 'dark' : 'light'}
        fitView
        fitViewOptions={{ padding: FIT_VIEW_PADDING }}
        minZoom={MIN_ZOOM}
        maxZoom={MAX_ZOOM}
        proOptions={{ hideAttribution: true }}
        // Performance optimizations
        nodesDraggable={false}
        onlyRenderVisibleElements
        snapToGrid
        snapGrid={SNAP_GRID}
      >
        <Background variant={BackgroundVariant.Dots} gap={BG_DOT_GAP} size={1} color="hsl(var(--border))" />
      </ReactFlow>
      {contextMenu && (
        <GraphNodeContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          nodeId={contextMenu.nodeId}
          isFocused={focusedNodeId === contextMenu.nodeId}
          onClose={handleCloseContextMenu}
          onOpenDocument={handleOpenDocument}
          onToggleFocus={handleToggleFocus}
        />
      )}
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
