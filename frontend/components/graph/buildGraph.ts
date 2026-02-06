/**
 * Pure functions for transforming API data (documents + dependencies) into
 * ReactFlow nodes and edges with nested folder grouping.
 *
 * Extracted from DependencyGraph.tsx so the component only handles rendering
 * and interaction, while this module owns the data transformation.
 */

import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';
import type { DocumentListItem } from '@/types';
import type { Dependency } from '@/lib/api/dependencies';
import type { GraphNodeData } from './GraphNode';

// --- Graph layout constants ---
// Changing these affects dagre auto-layout, node rendering, and group sizing.
export const NODE_WIDTH = 200;           // Pixels. Must match GraphNode min/max-width CSS.
export const NODE_HEIGHT = 40;           // Pixels. Affects vertical spacing in dagre layout.
export const GROUP_PADDING = 30;         // Pixels around children inside a group box.
export const GROUP_HEADER = 28;          // Pixels reserved for group label text.
const DAGRE_NODE_SEP = 60;              // Horizontal gap between sibling nodes in dagre layout.
const DAGRE_RANK_SEP = 80;              // Vertical gap between ranks (layers) in dagre layout.

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
  // Low opacity keeps group backgrounds subtle. Dark theme needs slightly
  // higher opacity (0.12) than light (0.08) to stay visible.
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
  g.setGraph({ rankdir: direction, nodesep: DAGRE_NODE_SEP, ranksep: DAGRE_RANK_SEP });

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

/** Rank nodes by connectivity (most connected first). */
function rankNodesByConnectivity(
  nodeIds: Set<string>,
  deps: Dependency[],
): string[] {
  const connectivity = new Map<string, number>();
  const nodeIdArray = Array.from(nodeIds);
  for (const id of nodeIdArray) connectivity.set(id, 0);

  for (const dep of deps) {
    if (nodeIds.has(dep.from_doc_id)) {
      connectivity.set(dep.from_doc_id, (connectivity.get(dep.from_doc_id) || 0) + 1);
    }
    if (nodeIds.has(dep.to_doc_id)) {
      connectivity.set(dep.to_doc_id, (connectivity.get(dep.to_doc_id) || 0) + 1);
    }
  }

  return nodeIdArray.sort((a, b) =>
    (connectivity.get(b) || 0) - (connectivity.get(a) || 0)
  );
}

/** Helper: create a group node wrapping a set of member nodes. */
function createGroupWithChildren(
  groupId: string,
  label: string,
  color: string,
  members: Node[],
): { groupNode: Node; childNodes: Node[] } {
  const minX = Math.min(...members.map((n) => n.position.x)) - GROUP_PADDING;
  const minY = Math.min(...members.map((n) => n.position.y)) - GROUP_PADDING - GROUP_HEADER;
  const maxX = Math.max(...members.map((n) => n.position.x + NODE_WIDTH)) + GROUP_PADDING;
  const maxY = Math.max(...members.map((n) => n.position.y + NODE_HEIGHT)) + GROUP_PADDING;
  const w = maxX - minX;
  const h = maxY - minY;

  const groupNode: Node = {
    id: groupId,
    type: 'group',
    position: { x: minX, y: minY },
    data: { label, color },
    width: w,
    height: h,
    style: {
      width: w, height: h,
      padding: 0, backgroundColor: 'transparent', border: 'none',
    },
  };

  const childNodes = members.map((member) => ({
    ...member,
    parentId: groupId,
    extent: 'parent' as const,
    position: {
      x: member.position.x - minX,
      y: member.position.y - minY,
    },
  }));

  return { groupNode, childNodes };
}

/** Transform API data into ReactFlow nodes and edges with nested folder grouping. */
export function buildGraph(
  docs: DocumentListItem[],
  deps: Dependency[],
  direction: 'TB' | 'LR',
  isDark: boolean,
  pathFilter: string,
  nodeLimit: number | null,
): { nodes: Node[]; edges: Edge[]; totalNodeCount: number } {
  // Collect all document IDs referenced by dependencies
  const referencedIds = new Set<string>();
  for (const dep of deps) {
    referencedIds.add(dep.from_doc_id);
    referencedIds.add(dep.to_doc_id);
  }

  const docMap = new Map(docs.map((d) => [d.id, d]));
  const normalizedFilter = pathFilter.trim().toLowerCase();

  // Build candidate node IDs, applying path filter
  const candidateIds = new Set<string>();
  for (const id of Array.from(referencedIds)) {
    const doc = docMap.get(id);
    if (!doc) continue;
    if (normalizedFilter && !doc.path.toLowerCase().startsWith(normalizedFilter)) continue;
    candidateIds.add(id);
  }

  const totalNodeCount = candidateIds.size;

  // Apply node limit - keep most connected nodes
  let limitedIds = candidateIds;
  if (nodeLimit !== null && candidateIds.size > nodeLimit) {
    const ranked = rankNodesByConnectivity(candidateIds, deps);
    limitedIds = new Set(ranked.slice(0, nodeLimit));
  }

  // Build document nodes
  const rawNodes: Node[] = [];
  const nodeToPath = new Map<string, string>();

  for (const id of Array.from(limitedIds)) {
    const doc = docMap.get(id)!;
    const folder = doc.path || '';
    nodeToPath.set(id, folder);
    rawNodes.push({
      id,
      type: 'document',
      position: { x: 0, y: 0 },
      zIndex: 10,
      data: {
        label: doc.title,
        path: doc.path,
        keywords: doc.keywords ?? [],
        direction,
      } satisfies GraphNodeData,
    });
  }

  const nodeIds = new Set(rawNodes.map((n) => n.id));

  // Deduplicate edges: one arrow per document pair (not per reference)
  const seenEdges = new Set<string>();
  const edges: Edge[] = [];
  for (const dep of deps) {
    if (!nodeIds.has(dep.from_doc_id) || !nodeIds.has(dep.to_doc_id)) continue;
    const key = `${dep.from_doc_id}->${dep.to_doc_id}`;
    if (seenEdges.has(key)) continue;
    seenEdges.add(key);
    edges.push({
      id: `e-${key}`,
      source: dep.from_doc_id,
      target: dep.to_doc_id,
      type: 'straight',
      zIndex: 0,
      style: { strokeWidth: 1 },
    });
  }

  if (rawNodes.length === 0) return { nodes: [], edges: [], totalNodeCount };

  // Run dagre on flat nodes first
  const laidOutNodes = layoutGraph(rawNodes, edges, direction);

  // Build nested folder hierarchy: L1 groups contain L2 subgroups
  // e.g. path "engineering/backend" -> L1="engineering", L2="engineering/backend"
  const l1Groups = new Map<string, Node[]>(); // L1 folder -> doc nodes with no L2
  const l2Groups = new Map<string, Node[]>(); // L2 folder -> doc nodes
  const l2ToL1 = new Map<string, string>();   // L2 folder -> L1 parent

  for (const node of laidOutNodes) {
    const fullPath = nodeToPath.get(node.id) || '';
    const segments = fullPath.split('/').filter(Boolean);
    const l1 = segments[0] || 'ungrouped';
    const l2 = segments.length >= 2 ? `${segments[0]}/${segments[1]}` : null;

    if (l2) {
      if (!l2Groups.has(l2)) l2Groups.set(l2, []);
      l2Groups.get(l2)!.push(node);
      l2ToL1.set(l2, l1);
    } else {
      if (!l1Groups.has(l1)) l1Groups.set(l1, []);
      l1Groups.get(l1)!.push(node);
    }
  }

  // Collect all L1 folders (including those that only have L2 children)
  const allL1 = new Set<string>();
  for (const l1 of Array.from(l1Groups.keys())) allL1.add(l1);
  for (const l1 of Array.from(l2ToL1.values())) allL1.add(l1);
  const sortedL1 = Array.from(allL1).sort();

  const allNodes: Node[] = [];
  let colorIndex = 0;

  for (const l1 of sortedL1) {
    const l1Color = getGroupColor(colorIndex++, isDark);
    const directMembers = l1Groups.get(l1) || [];

    // Find L2 subfolders under this L1
    const l2Folders = Array.from(l2Groups.keys())
      .filter((l2) => l2ToL1.get(l2) === l1)
      .sort();

    // If no L2 subfolders, just create a flat L1 group
    if (l2Folders.length === 0) {
      const { groupNode, childNodes } = createGroupWithChildren(
        `group-${l1}`, l1, l1Color, directMembers,
      );
      allNodes.push(groupNode, ...childNodes);
      continue;
    }

    // Create L2 subgroups first (not yet parented)
    const l2GroupNodes: Node[] = [];
    const l2ChildNodes: Node[] = [];

    for (const l2 of l2Folders) {
      const l2Members = l2Groups.get(l2)!;
      const l2Label = l2.split('/').slice(1).join('/'); // Show only subfolder name
      const l2Color = getGroupColor(colorIndex++, isDark);
      const { groupNode, childNodes } = createGroupWithChildren(
        `group-${l2}`, l2Label, l2Color, l2Members,
      );
      l2GroupNodes.push(groupNode);
      l2ChildNodes.push(...childNodes);
    }

    // Compute L1 bounding box around all direct members + L2 subgroup nodes
    const allContained = [...directMembers, ...l2GroupNodes];
    const minX = Math.min(...allContained.map((n) => n.position.x)) - GROUP_PADDING;
    const minY = Math.min(...allContained.map((n) => n.position.y)) - GROUP_PADDING - GROUP_HEADER;
    const maxX = Math.max(...allContained.map((n) => {
      const w = (n as { width?: number }).width || NODE_WIDTH;
      return n.position.x + w;
    })) + GROUP_PADDING;
    const maxY = Math.max(...allContained.map((n) => {
      const h = (n as { height?: number }).height || NODE_HEIGHT;
      return n.position.y + h;
    })) + GROUP_PADDING;

    const l1Width = maxX - minX;
    const l1Height = maxY - minY;

    // Create L1 group node
    const l1GroupNode: Node = {
      id: `group-${l1}`,
      type: 'group',
      position: { x: minX, y: minY },
      data: { label: l1, color: l1Color },
      width: l1Width,
      height: l1Height,
      style: {
        width: l1Width, height: l1Height,
        padding: 0, backgroundColor: 'transparent', border: 'none',
      },
    };
    allNodes.push(l1GroupNode);

    // Re-parent direct members to L1
    for (const member of directMembers) {
      member.parentId = l1GroupNode.id;
      member.extent = 'parent' as const;
      member.position = {
        x: member.position.x - minX,
        y: member.position.y - minY,
      };
      allNodes.push(member);
    }

    // Re-parent L2 groups to L1
    for (const l2Node of l2GroupNodes) {
      l2Node.parentId = l1GroupNode.id;
      l2Node.extent = 'parent' as const;
      l2Node.position = {
        x: l2Node.position.x - minX,
        y: l2Node.position.y - minY,
      };
      allNodes.push(l2Node);
    }

    // Add L2 children (already parented to their L2 group)
    allNodes.push(...l2ChildNodes);
  }

  return { nodes: allNodes, edges, totalNodeCount };
}
