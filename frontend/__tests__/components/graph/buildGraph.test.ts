import { describe, it, expect, vi } from 'vitest';
import type { DocumentListItem } from '@/types';
import type { Dependency } from '@/lib/api/dependencies';

// Mock dagre — buildGraph uses it for layout positioning
vi.mock('dagre', () => {
  let nodeCounter = 0;
  class MockGraph {
    setDefaultEdgeLabel() {}
    setGraph() {}
    setNode() {}
    setEdge() {}
    node() { return { x: nodeCounter++ * 250, y: nodeCounter * 50 }; }
  }
  return {
    default: {
      graphlib: { Graph: MockGraph },
      layout: vi.fn(),
    },
  };
});

import { buildGraph, NODE_WIDTH, NODE_HEIGHT } from '@/components/graph/buildGraph';

// --- Helpers ---

function makeDoc(overrides: Partial<DocumentListItem> & { id: string; path: string; title: string }): DocumentListItem {
  return {
    keywords: [],
    content_preview: '',
    updated_at: '2025-01-01T00:00:00',
    generation_count: 0,
    version: 1,
    ...overrides,
  };
}

function makeDep(from: string, to: string, id = 1): Dependency {
  return {
    id,
    from_doc_id: from,
    to_doc_id: to,
    link_type: 'wikilink',
    link_text: null,
    section: null,
    created_at: '2025-01-01',
  };
}

describe('buildGraph', () => {
  it('returns empty graph when there are no dependencies', () => {
    const docs = [makeDoc({ id: 'a', path: 'eng', title: 'A' })];
    const result = buildGraph(docs, [], 'TB', false, '', null);

    expect(result.nodes).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
    expect(result.totalNodeCount).toBe(0);
  });

  it('returns empty graph when deps reference docs not in the list', () => {
    const docs = [makeDoc({ id: 'a', path: 'eng', title: 'A' })];
    const deps = [makeDep('x', 'y')]; // x and y not in docs
    const result = buildGraph(docs, deps, 'TB', false, '', null);

    expect(result.nodes).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
  });

  it('creates nodes and edges for connected documents', () => {
    const docs = [
      makeDoc({ id: 'a', path: 'eng', title: 'Doc A' }),
      makeDoc({ id: 'b', path: 'eng', title: 'Doc B' }),
    ];
    const deps = [makeDep('a', 'b')];
    const result = buildGraph(docs, deps, 'TB', false, '', null);

    // Should have document nodes + group node(s)
    const docNodes = result.nodes.filter((n) => n.type === 'document');
    const groupNodes = result.nodes.filter((n) => n.type === 'group');

    expect(docNodes).toHaveLength(2);
    expect(groupNodes.length).toBeGreaterThanOrEqual(1);
    expect(result.edges).toHaveLength(1);
    expect(result.edges[0].source).toBe('a');
    expect(result.edges[0].target).toBe('b');
    expect(result.totalNodeCount).toBe(2);
  });

  it('deduplicates edges between the same pair of documents', () => {
    const docs = [
      makeDoc({ id: 'a', path: 'eng', title: 'A' }),
      makeDoc({ id: 'b', path: 'eng', title: 'B' }),
    ];
    const deps = [makeDep('a', 'b', 1), makeDep('a', 'b', 2)];
    const result = buildGraph(docs, deps, 'TB', false, '', null);

    expect(result.edges).toHaveLength(1);
  });

  it('filters nodes by path prefix', () => {
    const docs = [
      makeDoc({ id: 'a', path: 'engineering/backend', title: 'A' }),
      makeDoc({ id: 'b', path: 'engineering/frontend', title: 'B' }),
      makeDoc({ id: 'c', path: 'marketing/brand', title: 'C' }),
    ];
    const deps = [makeDep('a', 'b'), makeDep('a', 'c')];
    const result = buildGraph(docs, deps, 'TB', false, 'engineering', null);

    const docNodes = result.nodes.filter((n) => n.type === 'document');
    expect(docNodes).toHaveLength(2);
    expect(docNodes.map((n) => n.id).sort()).toEqual(['a', 'b']);
    // totalNodeCount reflects filtered set
    expect(result.totalNodeCount).toBe(2);
  });

  it('respects node limit by keeping most connected nodes', () => {
    const docs = [
      makeDoc({ id: 'hub', path: 'eng', title: 'Hub' }),
      makeDoc({ id: 'a', path: 'eng', title: 'A' }),
      makeDoc({ id: 'b', path: 'eng', title: 'B' }),
      makeDoc({ id: 'c', path: 'eng', title: 'C' }),
    ];
    // hub connects to all three, a/b/c only connect to hub
    const deps = [makeDep('hub', 'a', 1), makeDep('hub', 'b', 2), makeDep('hub', 'c', 3)];

    const result = buildGraph(docs, deps, 'TB', false, '', 2);
    const docNodes = result.nodes.filter((n) => n.type === 'document');

    expect(docNodes.length).toBeLessThanOrEqual(2);
    // Hub should always be included (most connected)
    expect(docNodes.some((n) => n.id === 'hub')).toBe(true);
    expect(result.totalNodeCount).toBe(4); // Total before limiting
  });

  it('creates folder groups based on path hierarchy', () => {
    const docs = [
      makeDoc({ id: 'a', path: 'engineering/backend', title: 'A' }),
      makeDoc({ id: 'b', path: 'engineering/frontend', title: 'B' }),
      makeDoc({ id: 'c', path: 'marketing', title: 'C' }),
    ];
    const deps = [makeDep('a', 'b'), makeDep('a', 'c')];
    const result = buildGraph(docs, deps, 'TB', false, '', null);

    const groupNodes = result.nodes.filter((n) => n.type === 'group');
    const groupLabels = groupNodes.map((n) => (n.data as { label: string }).label);

    // Should have L1 groups for "engineering" and "marketing",
    // plus L2 subgroups for "backend" and "frontend"
    expect(groupLabels).toContain('engineering');
    expect(groupLabels).toContain('marketing');
  });

  it('sets document node data with title, path, and keywords', () => {
    const docs = [
      makeDoc({ id: 'a', path: 'eng', title: 'Doc A', keywords: ['api', 'rest'] }),
      makeDoc({ id: 'b', path: 'eng', title: 'Doc B' }),
    ];
    const deps = [makeDep('a', 'b')];
    const result = buildGraph(docs, deps, 'TB', false, '', null);

    const nodeA = result.nodes.find((n) => n.id === 'a');
    expect(nodeA).toBeDefined();
    expect((nodeA!.data as { label: string }).label).toBe('Doc A');
    expect((nodeA!.data as { path: string }).path).toBe('eng');
    expect((nodeA!.data as { keywords: string[] }).keywords).toEqual(['api', 'rest']);
  });

  it('uses straight edge type', () => {
    const docs = [
      makeDoc({ id: 'a', path: 'eng', title: 'A' }),
      makeDoc({ id: 'b', path: 'eng', title: 'B' }),
    ];
    const deps = [makeDep('a', 'b')];
    const result = buildGraph(docs, deps, 'TB', false, '', null);

    expect(result.edges[0].type).toBe('straight');
  });

  it('only includes edges where both endpoints are in the node set', () => {
    const docs = [
      makeDoc({ id: 'a', path: 'eng', title: 'A' }),
      makeDoc({ id: 'b', path: 'eng', title: 'B' }),
    ];
    // Dep references 'c' which is not in docs
    const deps = [makeDep('a', 'b'), makeDep('a', 'c')];
    const result = buildGraph(docs, deps, 'TB', false, '', null);

    expect(result.edges).toHaveLength(1);
    expect(result.edges[0].source).toBe('a');
    expect(result.edges[0].target).toBe('b');
  });

  it('exports layout constants', () => {
    expect(NODE_WIDTH).toBe(200);
    expect(NODE_HEIGHT).toBe(40);
  });
});
