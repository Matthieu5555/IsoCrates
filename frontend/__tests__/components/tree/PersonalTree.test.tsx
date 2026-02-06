import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PersonalTree } from '@/components/tree/PersonalTree';
import type { PersonalTreeNode } from '@/types';

// Mock API modules
vi.mock('@/lib/api/personal', () => ({
  getPersonalTree: vi.fn(),
  createPersonalFolder: vi.fn(),
  deletePersonalFolder: vi.fn(),
  removeDocumentRef: vi.fn(),
  movePersonalFolder: vi.fn(),
  moveDocumentRef: vi.fn(),
}));

vi.mock('@/lib/api/client', () => ({
  fetchApi: vi.fn(),
  getApiErrorMessage: (err: unknown) =>
    err instanceof Error ? err.message : 'An unexpected error occurred',
}));

vi.mock('@/lib/notifications/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock('@/lib/styles/button-variants', () => ({
  buttonVariants: { iconSmall: 'btn-sm' },
  iconVariants: { folder: 'ic-folder', document: 'ic-doc' },
  contextMenuVariants: { container: 'ctx-menu', divider: 'ctx-div' },
  menuItemVariants: { default: 'mi-default', danger: 'mi-danger' },
  overlayVariants: { loading: 'overlay-loading', dropTarget: 'overlay-drop' },
}));

// Mock dialog sub-components
vi.mock('@/components/tree/dialogs/NewFolderDialog', () => ({
  NewFolderDialog: () => null,
}));
vi.mock('@/components/tree/dialogs/AddDocumentDialog', () => ({
  AddDocumentDialog: () => null,
}));
vi.mock('@/components/tree/dialogs/ConfirmDialog', () => ({
  ConfirmDialog: () => null,
}));

import { getPersonalTree } from '@/lib/api/personal';
const mockGetPersonalTree = vi.mocked(getPersonalTree);

const sampleTree: PersonalTreeNode[] = [
  {
    id: 'pf-1',
    name: 'My Notes',
    type: 'folder',
    folder_id: 'pf-1',
    children: [
      {
        id: 'pr-1',
        name: 'Architecture Overview',
        type: 'document',
        document_id: 'doc-arch',
        ref_id: 'ref-1',
        children: [],
      },
      {
        id: 'pr-2',
        name: 'API Guide',
        type: 'document',
        document_id: 'doc-api',
        ref_id: 'ref-2',
        children: [],
      },
    ],
  },
  {
    id: 'pf-2',
    name: 'Work',
    type: 'folder',
    folder_id: 'pf-2',
    children: [],
  },
];

describe('PersonalTree', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('loading state', () => {
    it('shows loading text while tree data is being fetched', () => {
      mockGetPersonalTree.mockReturnValue(new Promise(() => {}));
      render(<PersonalTree />);
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows error message and retry button when fetch fails', async () => {
      mockGetPersonalTree.mockRejectedValue(new Error('Network failure'));

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByText('Could not load documents')).toBeInTheDocument();
      });
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    it('retries loading when retry button is clicked', async () => {
      mockGetPersonalTree
        .mockRejectedValueOnce(new Error('Network failure'))
        .mockResolvedValueOnce(sampleTree);

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByText('Could not load documents')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Retry'));

      await waitFor(() => {
        expect(screen.getByText('My Notes')).toBeInTheDocument();
      });
      expect(mockGetPersonalTree).toHaveBeenCalledTimes(2);
    });
  });

  describe('tree rendering', () => {
    it('renders top-level folders from tree data', async () => {
      mockGetPersonalTree.mockResolvedValue(sampleTree);

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByText('My Notes')).toBeInTheDocument();
        expect(screen.getByText('Work')).toBeInTheDocument();
      });
    });

    it('renders child documents when folder is expanded', async () => {
      mockGetPersonalTree.mockResolvedValue(sampleTree);

      render(<PersonalTree />);

      // Top-level folders are auto-expanded on initial load
      await waitFor(() => {
        expect(screen.getByText('Architecture Overview')).toBeInTheDocument();
        expect(screen.getByText('API Guide')).toBeInTheDocument();
      });
    });

    it('shows empty state when tree has no folders', async () => {
      mockGetPersonalTree.mockResolvedValue([]);

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByText('No personal folders yet')).toBeInTheDocument();
      });
    });
  });

  describe('expand and collapse', () => {
    it('collapses folder when clicked and hides children', async () => {
      mockGetPersonalTree.mockResolvedValue(sampleTree);

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByText('Architecture Overview')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('My Notes'));

      expect(screen.queryByText('Architecture Overview')).not.toBeInTheDocument();
      expect(screen.queryByText('API Guide')).not.toBeInTheDocument();
    });

    it('re-expands folder when clicked again', async () => {
      mockGetPersonalTree.mockResolvedValue(sampleTree);

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByText('Architecture Overview')).toBeInTheDocument();
      });

      // Collapse then re-expand
      fireEvent.click(screen.getByText('My Notes'));
      expect(screen.queryByText('Architecture Overview')).not.toBeInTheDocument();

      fireEvent.click(screen.getByText('My Notes'));
      expect(screen.getByText('Architecture Overview')).toBeInTheDocument();
    });
  });

  describe('toolbar actions', () => {
    it('renders toolbar buttons', async () => {
      mockGetPersonalTree.mockResolvedValue(sampleTree);

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByTitle('New Folder')).toBeInTheDocument();
        expect(screen.getByTitle('Add Document')).toBeInTheDocument();
        expect(screen.getByTitle('Refresh')).toBeInTheDocument();
      });
    });

    it('refresh button re-fetches tree data', async () => {
      mockGetPersonalTree.mockResolvedValue(sampleTree);

      render(<PersonalTree />);

      await waitFor(() => {
        expect(screen.getByText('My Notes')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTitle('Refresh'));

      await waitFor(() => {
        expect(mockGetPersonalTree).toHaveBeenCalledTimes(2);
      });
    });
  });
});
