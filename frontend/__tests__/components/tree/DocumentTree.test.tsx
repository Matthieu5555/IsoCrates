import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentTree } from '@/components/tree/DocumentTree';
import type { TreeNode } from '@/types';

// Mock API modules
vi.mock('@/lib/api/documents', () => ({
  getTree: vi.fn(),
  getTrash: vi.fn().mockResolvedValue([]),
  deleteDocument: vi.fn(),
  createDocument: vi.fn(),
  moveFolder: vi.fn(),
  moveDocument: vi.fn(),
  createFolderMetadata: vi.fn(),
  deleteFolder: vi.fn(),
  executeBatch: vi.fn(),
}));

vi.mock('@/lib/api/client', () => ({
  fetchApi: vi.fn().mockResolvedValue([]),
  getApiErrorMessage: (err: unknown) =>
    err instanceof Error ? err.message : 'An unexpected error occurred',
}));

// Mock toast notifications
vi.mock('@/lib/notifications/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock button-variants (simple passthrough strings)
vi.mock('@/lib/styles/button-variants', () => ({
  buttonVariants: { iconSmall: 'btn-sm', primary: 'btn-primary' },
  iconVariants: { folderCrate: 'ic-crate', folder: 'ic-folder', document: 'ic-doc' },
  overlayVariants: { loading: 'overlay-loading', dropTarget: 'overlay-drop' },
}));

// Mock dialog sub-components so they don't interfere with tree tests
vi.mock('@/components/tree/dialogs/NewDocumentDialog', () => ({
  NewDocumentDialog: () => null,
}));
vi.mock('@/components/tree/dialogs/NewFolderDialog', () => ({
  NewFolderDialog: () => null,
}));
vi.mock('@/components/tree/dialogs/ConfirmDialog', () => ({
  ConfirmDialog: () => null,
}));
vi.mock('@/components/tree/dialogs/DeleteFolderDialog', () => ({
  DeleteFolderDialog: () => null,
}));
vi.mock('@/components/tree/dialogs/FolderPickerDialog', () => ({
  FolderPickerDialog: () => null,
}));
vi.mock('@/components/tree/BulkActionBar', () => ({
  BulkActionBar: () => null,
}));
vi.mock('@/components/tree/ContextMenu', () => ({
  ContextMenu: () => null,
}));

import { getTree } from '@/lib/api/documents';
const mockGetTree = vi.mocked(getTree);

// Sample tree data
const sampleTree: TreeNode[] = [
  {
    id: 'folder-eng',
    name: 'engineering',
    type: 'folder',
    path: 'engineering',
    children: [
      {
        id: 'doc-arch',
        name: 'Architecture',
        type: 'document',
        path: 'engineering',
        children: [],
      },
      {
        id: 'doc-api',
        name: 'API Guide',
        type: 'document',
        path: 'engineering',
        children: [],
      },
    ],
  },
  {
    id: 'folder-design',
    name: 'design',
    type: 'folder',
    path: 'design',
    children: [
      {
        id: 'doc-ui',
        name: 'UI Patterns',
        type: 'document',
        path: 'design',
        children: [],
      },
    ],
  },
];

describe('DocumentTree', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('loading state', () => {
    it('shows loading text while tree data is being fetched', () => {
      mockGetTree.mockReturnValue(new Promise(() => {}));

      render(<DocumentTree />);
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows error message and retry button when getTree fails', async () => {
      mockGetTree.mockRejectedValue(new Error('Network failure'));

      render(<DocumentTree />);

      await waitFor(() => {
        expect(screen.getByText('Could not load documents')).toBeInTheDocument();
      });
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    it('retries loading when retry button is clicked', async () => {
      // First call fails, second succeeds
      mockGetTree
        .mockRejectedValueOnce(new Error('Network failure'))
        .mockResolvedValueOnce(sampleTree);

      render(<DocumentTree />);

      await waitFor(() => {
        expect(screen.getByText('Could not load documents')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Retry'));

      await waitFor(() => {
        expect(screen.getByText('engineering')).toBeInTheDocument();
      });
      expect(mockGetTree).toHaveBeenCalledTimes(2);
    });
  });

  describe('tree rendering', () => {
    it('renders top-level folders from tree data', async () => {
      mockGetTree.mockResolvedValue(sampleTree);

      render(<DocumentTree />);

      await waitFor(() => {
        expect(screen.getByText('engineering')).toBeInTheDocument();
        expect(screen.getByText('design')).toBeInTheDocument();
      });
    });

    it('shows document count for folder nodes', async () => {
      mockGetTree.mockResolvedValue(sampleTree);

      render(<DocumentTree />);

      await waitFor(() => {
        // engineering has 2 documents, design has 1
        expect(screen.getByText('2')).toBeInTheDocument();
        expect(screen.getByText('1')).toBeInTheDocument();
      });
    });

    it('renders child documents when folder is expanded', async () => {
      mockGetTree.mockResolvedValue(sampleTree);

      render(<DocumentTree />);

      // Top-level folders are auto-expanded on initial load
      await waitFor(() => {
        expect(screen.getByText('Architecture')).toBeInTheDocument();
        expect(screen.getByText('API Guide')).toBeInTheDocument();
        expect(screen.getByText('UI Patterns')).toBeInTheDocument();
      });
    });
  });

  describe('expand and collapse', () => {
    it('collapses folder when clicked and hides children', async () => {
      mockGetTree.mockResolvedValue(sampleTree);

      render(<DocumentTree />);

      // Wait for tree to render with folders expanded
      await waitFor(() => {
        expect(screen.getByText('Architecture')).toBeInTheDocument();
      });

      // Click the engineering folder to collapse it
      fireEvent.click(screen.getByText('engineering'));

      // Children should be hidden
      expect(screen.queryByText('Architecture')).not.toBeInTheDocument();
      expect(screen.queryByText('API Guide')).not.toBeInTheDocument();
    });

    it('re-expands folder when clicked again', async () => {
      mockGetTree.mockResolvedValue(sampleTree);

      render(<DocumentTree />);

      await waitFor(() => {
        expect(screen.getByText('Architecture')).toBeInTheDocument();
      });

      // Collapse
      fireEvent.click(screen.getByText('engineering'));
      expect(screen.queryByText('Architecture')).not.toBeInTheDocument();

      // Re-expand
      fireEvent.click(screen.getByText('engineering'));
      expect(screen.getByText('Architecture')).toBeInTheDocument();
      expect(screen.getByText('API Guide')).toBeInTheDocument();
    });
  });

  describe('toolbar actions', () => {
    it('renders New Document and New Folder buttons', async () => {
      mockGetTree.mockResolvedValue(sampleTree);

      render(<DocumentTree />);

      await waitFor(() => {
        expect(screen.getByTitle('New Document')).toBeInTheDocument();
        expect(screen.getByTitle('New Folder')).toBeInTheDocument();
        expect(screen.getByTitle('Refresh')).toBeInTheDocument();
      });
    });

    it('refresh button re-fetches tree data', async () => {
      mockGetTree.mockResolvedValue(sampleTree);

      render(<DocumentTree />);

      await waitFor(() => {
        expect(screen.getByText('engineering')).toBeInTheDocument();
      });

      // Click refresh
      fireEvent.click(screen.getByTitle('Refresh'));

      // getTree should be called again (initial load + refresh)
      await waitFor(() => {
        expect(mockGetTree).toHaveBeenCalledTimes(2);
      });
    });
  });
});
