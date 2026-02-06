import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { DependencyGraph } from '@/components/graph/DependencyGraph';

// Mock next-themes
vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

// Mock @xyflow/react - provide minimal implementations for ReactFlow and its hooks
vi.mock('@xyflow/react', () => {
  const ReactFlowProvider = ({ children }: { children: React.ReactNode }) => <div>{children}</div>;
  const ReactFlow = ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="react-flow">{children}</div>
  );
  const Background = () => <div data-testid="rf-background" />;
  return {
    ReactFlow,
    ReactFlowProvider,
    Background,
    BackgroundVariant: { Dots: 'dots' },
    useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
    useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
    useReactFlow: () => ({
      fitView: vi.fn(),
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
    }),
  };
});

// Mock dagre — use a real class so `new dagre.graphlib.Graph()` works
vi.mock('dagre', () => {
  class MockGraph {
    setDefaultEdgeLabel() {}
    setGraph() {}
    setNode() {}
    setEdge() {}
    node() { return { x: 0, y: 0 }; }
  }
  const dagre = {
    graphlib: { Graph: MockGraph },
    layout: vi.fn(),
  };
  return { default: dagre, ...dagre };
});

// Mock sub-components to isolate the graph logic
vi.mock('@/components/graph/GraphNode', () => ({
  GraphNode: () => <div data-testid="graph-node" />,
}));
vi.mock('@/components/graph/GraphGroupNode', () => ({
  GraphGroupNode: () => <div data-testid="graph-group-node" />,
}));
vi.mock('@/components/graph/GraphControls', () => ({
  GraphControls: () => <div data-testid="graph-controls" />,
}));
vi.mock('@/components/graph/GraphNodeContextMenu', () => ({
  GraphNodeContextMenu: () => null,
}));

// Mock API modules
vi.mock('@/lib/api/dependencies', () => ({
  getAllDependencies: vi.fn(),
}));
vi.mock('@/lib/api/documents', () => ({
  getDocuments: vi.fn(),
}));
vi.mock('@/lib/api/client', () => ({
  getApiErrorMessage: (err: unknown) =>
    err instanceof Error ? err.message : 'An unexpected error occurred',
}));

import { getAllDependencies } from '@/lib/api/dependencies';
import { getDocuments } from '@/lib/api/documents';

const mockGetAllDependencies = vi.mocked(getAllDependencies);
const mockGetDocuments = vi.mocked(getDocuments);

describe('DependencyGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    // Make API calls hang so we stay in loading state
    mockGetDocuments.mockReturnValue(new Promise(() => {}));
    mockGetAllDependencies.mockReturnValue(new Promise(() => {}));

    render(<DependencyGraph />);
    expect(screen.getByText('Loading graph...')).toBeInTheDocument();
  });

  it('shows empty state when there are no dependencies', async () => {
    mockGetDocuments.mockResolvedValue([]);
    mockGetAllDependencies.mockResolvedValue([]);

    render(<DependencyGraph />);

    await waitFor(() => {
      expect(
        screen.getByText(/No document dependencies found/)
      ).toBeInTheDocument();
    });
  });

  it('shows error state with retry button when both API calls fail', async () => {
    mockGetDocuments.mockRejectedValue(new Error('Connection refused'));
    mockGetAllDependencies.mockRejectedValue(new Error('Connection refused'));

    render(<DependencyGraph />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load dependency graph')).toBeInTheDocument();
    });
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('renders ReactFlow when data is available', async () => {
    const docs = [
      {
        id: 'doc-1', path: 'engineering', title: 'Doc A',
        keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1,
      },
      {
        id: 'doc-2', path: 'engineering', title: 'Doc B',
        keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1,
      },
    ];
    const deps = [
      {
        id: 1, from_doc_id: 'doc-1', to_doc_id: 'doc-2',
        link_type: 'wikilink', link_text: 'Doc B', section: null, created_at: '',
      },
    ];

    mockGetDocuments.mockResolvedValue(docs);
    mockGetAllDependencies.mockResolvedValue(deps);

    render(<DependencyGraph />);

    await waitFor(() => {
      expect(screen.getByTestId('react-flow')).toBeInTheDocument();
    });
    expect(screen.getByTestId('graph-controls')).toBeInTheDocument();
  });

  it('gracefully handles partial API failures (only docs fail)', async () => {
    // When only getDocuments fails, the graph should still render
    // (with whatever deps are available, but no matching docs => empty graph)
    mockGetDocuments.mockRejectedValue(new Error('Docs failed'));
    mockGetAllDependencies.mockResolvedValue([
      {
        id: 1, from_doc_id: 'a', to_doc_id: 'b',
        link_type: 'wikilink', link_text: null, section: null, created_at: '',
      },
    ]);

    render(<DependencyGraph />);

    // With deps but no doc lookup, buildGraph can't match IDs so shows empty message
    await waitFor(() => {
      expect(
        screen.queryByText('Failed to load dependency graph')
      ).not.toBeInTheDocument();
    });
  });
});
