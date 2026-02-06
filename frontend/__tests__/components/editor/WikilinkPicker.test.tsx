import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WikilinkPicker } from '@/components/editor/WikilinkPicker';

// Mock the API modules
vi.mock('@/lib/api/documents', () => ({
  searchDocuments: vi.fn(),
  getRecentDocuments: vi.fn().mockResolvedValue([]),
}));

import { searchDocuments, getRecentDocuments } from '@/lib/api/documents';

const mockSearchDocuments = vi.mocked(searchDocuments);
const mockGetRecentDocuments = vi.mocked(getRecentDocuments);

function createAnchorRef(): React.RefObject<HTMLButtonElement | null> {
  const button = document.createElement('button');
  button.getBoundingClientRect = () => ({
    top: 100, bottom: 140, left: 200, right: 240,
    width: 40, height: 40, x: 200, y: 100,
    toJSON: () => {},
  });
  document.body.appendChild(button);
  return { current: button };
}

describe('WikilinkPicker', () => {
  let anchorRef: React.RefObject<HTMLButtonElement | null>;
  const onClose = vi.fn();
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetRecentDocuments.mockResolvedValue([]);
    anchorRef = createAnchorRef();
  });

  describe('rendering', () => {
    it('renders nothing when open is false', () => {
      const { container } = render(
        <WikilinkPicker anchorRef={anchorRef} open={false} onClose={onClose} onSelect={onSelect} />
      );
      expect(container.innerHTML).toBe('');
    });

    it('renders a search input when open is true', () => {
      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );
      expect(screen.getByPlaceholderText('Search documents to link...')).toBeInTheDocument();
    });

    it('loads recent documents when opened', async () => {
      const recentDocs = [
        { id: '1', title: 'Getting Started', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
        { id: '2', title: 'API Guide', path: 'docs/api', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
      ];
      mockGetRecentDocuments.mockResolvedValue(recentDocs);

      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      await waitFor(() => {
        expect(screen.getByText('Getting Started')).toBeInTheDocument();
        expect(screen.getByText('API Guide')).toBeInTheDocument();
      });
    });
  });

  describe('search', () => {
    it('shows "No documents found" when query >= 2 chars and no results', async () => {
      mockSearchDocuments.mockResolvedValue([]);

      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      const input = screen.getByPlaceholderText('Search documents to link...');
      fireEvent.change(input, { target: { value: 'nonexistent' } });

      await waitFor(() => {
        expect(screen.getByText('No documents found')).toBeInTheDocument();
      });
    });

    it('displays search results returned from API', async () => {
      const searchResults = [
        { id: '10', title: 'Architecture Overview', path: 'engineering', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
      ];
      mockSearchDocuments.mockResolvedValue(searchResults);

      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      const input = screen.getByPlaceholderText('Search documents to link...');
      fireEvent.change(input, { target: { value: 'architecture' } });

      await waitFor(() => {
        expect(screen.getByText('Architecture Overview')).toBeInTheDocument();
      });
    });
  });

  describe('item selection', () => {
    it('calls onSelect and onClose when a result is clicked', async () => {
      const docs = [
        { id: '1', title: 'My Document', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
      ];
      mockGetRecentDocuments.mockResolvedValue(docs);

      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      await waitFor(() => {
        expect(screen.getByText('My Document')).toBeInTheDocument();
      });

      // Use mouseDown since the component uses onMouseDown
      fireEvent.mouseDown(screen.getByText('My Document'));

      expect(onSelect).toHaveBeenCalledWith('My Document');
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('keyboard navigation', () => {
    it('closes on Escape key', async () => {
      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      const input = screen.getByPlaceholderText('Search documents to link...');
      fireEvent.keyDown(input, { key: 'Escape' });

      expect(onClose).toHaveBeenCalled();
    });

    it('navigates results with ArrowDown and ArrowUp', async () => {
      const docs = [
        { id: '1', title: 'Doc Alpha', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
        { id: '2', title: 'Doc Beta', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
        { id: '3', title: 'Doc Gamma', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
      ];
      mockGetRecentDocuments.mockResolvedValue(docs);

      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      await waitFor(() => {
        expect(screen.getByText('Doc Alpha')).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText('Search documents to link...');

      // Initially selectedIndex is 0 (Doc Alpha highlighted)
      // Press ArrowDown to move to index 1 (Doc Beta)
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      // Press ArrowDown again to move to index 2 (Doc Gamma)
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      // Press Enter to select Doc Gamma
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(onSelect).toHaveBeenCalledWith('Doc Gamma');
    });

    it('does not go below the last item on ArrowDown', async () => {
      const docs = [
        { id: '1', title: 'Only Doc', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
      ];
      mockGetRecentDocuments.mockResolvedValue(docs);

      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      await waitFor(() => {
        expect(screen.getByText('Only Doc')).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText('Search documents to link...');

      // Press ArrowDown multiple times - should stay on index 0
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(onSelect).toHaveBeenCalledWith('Only Doc');
    });

    it('selects first item on Enter when results exist', async () => {
      const docs = [
        { id: '1', title: 'First Doc', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
        { id: '2', title: 'Second Doc', path: 'docs', keywords: [], content_preview: '', updated_at: '', generation_count: 0, version: 1 },
      ];
      mockGetRecentDocuments.mockResolvedValue(docs);

      render(
        <WikilinkPicker anchorRef={anchorRef} open={true} onClose={onClose} onSelect={onSelect} />
      );

      await waitFor(() => {
        expect(screen.getByText('First Doc')).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText('Search documents to link...');
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(onSelect).toHaveBeenCalledWith('First Doc');
      expect(onClose).toHaveBeenCalled();
    });
  });
});
