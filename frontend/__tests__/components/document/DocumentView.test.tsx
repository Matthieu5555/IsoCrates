import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentView } from '@/components/document/DocumentView';
import { ApiError } from '@/lib/api/client';
import type { Document } from '@/types';

// Mock API modules
vi.mock('@/lib/api/documents', () => ({
  updateDocument: vi.fn(),
  deleteDocument: vi.fn(),
  getDocument: vi.fn(),
  getDocumentVersions: vi.fn().mockResolvedValue([]),
}));

vi.mock('@/lib/api/client', () => ({
  ApiError: class extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
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
  buttonVariants: { primary: 'btn-primary', secondary: 'btn-secondary', icon: 'btn-icon' },
  badgeVariants: { keyword: 'badge-kw', keywordAdd: 'badge-add' },
  inputVariants: { default: 'input-default' },
  linkVariants: { external: 'link-ext' },
  scrollContainerVariants: { horizontal: 'scroll-h' },
  tableVariants: { row: 'tbl-row', cell: 'tbl-cell' },
  textVariants: { mutedXs: 'txt-muted' },
}));

// Mock complex child components
vi.mock('@/components/document/MetadataDigest', () => ({
  MetadataDigest: ({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) => (
    <div>
      <button onClick={onEdit}>Edit</button>
      <button onClick={onDelete}>Delete</button>
    </div>
  ),
}));

vi.mock('@/components/document/MetadataDetails', () => ({
  MetadataDetails: () => <div data-testid="metadata-details" />,
}));

vi.mock('@/components/document/VersionHistory', () => ({
  VersionHistory: () => <div data-testid="version-history" />,
}));

vi.mock('@/components/markdown/MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => (
    <div data-testid="markdown-renderer">{content}</div>
  ),
}));

vi.mock('@/components/editor/MarkdownEditor', () => ({
  MarkdownEditor: ({ content, onChange }: { content: string; onChange: (v: string) => void }) => (
    <textarea
      data-testid="markdown-editor"
      value={content}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

vi.mock('@/components/tree/dialogs/ConfirmDialog', () => ({
  ConfirmDialog: ({ open, onConfirm }: { open: boolean; onConfirm: () => void }) =>
    open ? <button data-testid="confirm-delete" onClick={onConfirm}>Confirm Delete</button> : null,
}));

import { updateDocument, getDocument } from '@/lib/api/documents';
import { toast } from '@/lib/notifications/toast';

const mockUpdateDocument = vi.mocked(updateDocument);
const mockGetDocument = vi.mocked(getDocument);

const sampleDoc: Document = {
  id: 'doc-123',
  repo_url: 'https://github.com/org/repo',
  repo_name: 'repo',
  path: 'engineering',
  title: 'Architecture Overview',
  content: '# Architecture\n\nThis is the architecture document.',
  doc_type: 'architecture',
  keywords: ['Technical Docs'],
  content_preview: 'Architecture document...',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-15T00:00:00Z',
  generation_count: 3,
  version: 5,
};

describe('DocumentView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders document content in view mode', () => {
      render(<DocumentView document={sampleDoc} />);
      expect(screen.getByTestId('markdown-renderer')).toHaveTextContent('Architecture');
      expect(screen.getByTestId('metadata-details')).toBeInTheDocument();
      expect(screen.getByTestId('version-history')).toBeInTheDocument();
    });
  });

  describe('edit mode', () => {
    it('switches to editor when Edit is clicked', async () => {
      render(<DocumentView document={sampleDoc} />);

      fireEvent.click(screen.getByText('Edit'));

      await waitFor(() => {
        expect(screen.getByTestId('markdown-editor')).toBeInTheDocument();
      });
    });
  });

  describe('save', () => {
    it('calls updateDocument and shows success toast on save', async () => {
      const updatedDoc = { ...sampleDoc, version: 6, content: 'Updated content' };
      mockUpdateDocument.mockResolvedValue(updatedDoc);

      render(<DocumentView document={sampleDoc} />);

      // Enter edit mode
      fireEvent.click(screen.getByText('Edit'));

      await waitFor(() => {
        expect(screen.getByTestId('markdown-editor')).toBeInTheDocument();
      });

      // Click save
      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(mockUpdateDocument).toHaveBeenCalledWith(
          'doc-123',
          sampleDoc.content,
          undefined,
          5,
        );
        expect(toast.success).toHaveBeenCalledWith(
          'Document saved',
          expect.any(String),
        );
      });
    });

    it('handles 409 conflict by refreshing from server', async () => {
      const conflictError = new (ApiError as any)(409, 'Version conflict');
      mockUpdateDocument.mockRejectedValue(conflictError);

      const latestDoc = { ...sampleDoc, version: 7, content: 'Newer content from someone else' };
      mockGetDocument.mockResolvedValue(latestDoc);

      render(<DocumentView document={sampleDoc} />);

      // Enter edit mode
      fireEvent.click(screen.getByText('Edit'));

      await waitFor(() => {
        expect(screen.getByTestId('markdown-editor')).toBeInTheDocument();
      });

      // Save triggers conflict
      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(mockGetDocument).toHaveBeenCalledWith('doc-123');
        expect(toast.error).toHaveBeenCalledWith(
          'Conflict detected',
          expect.stringContaining('modified'),
        );
      });
    });

    it('shows generic error toast on non-conflict save failure', async () => {
      mockUpdateDocument.mockRejectedValue(new Error('Network failure'));

      render(<DocumentView document={sampleDoc} />);

      fireEvent.click(screen.getByText('Edit'));

      await waitFor(() => {
        expect(screen.getByTestId('markdown-editor')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'Failed to save document',
          expect.any(String),
        );
      });
    });
  });
});
