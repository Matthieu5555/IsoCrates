'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Search } from 'lucide-react';
import { searchDocuments, getRecentDocuments, type SearchResult } from '@/lib/api/documents';
import type { DocumentListItem } from '@/types';

interface WikilinkPickerProps {
  /** Anchor element the popover attaches to */
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  open: boolean;
  onClose: () => void;
  onSelect: (title: string) => void;
}

/**
 * Popover for searching and selecting a document to insert as a [[wikilink]].
 *
 * Opens below the toolbar @ button. Shows recent documents initially, then
 * switches to search results as the user types. Keyboard navigation with
 * ArrowUp/Down and Enter to select. Escape or clicking outside closes it.
 */
export function WikilinkPicker({ anchorRef, open, onClose, onSelect }: WikilinkPickerProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<(SearchResult | DocumentListItem)[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Position state
  const [position, setPosition] = useState({ top: 0, left: 0 });

  // Calculate position from anchor
  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPosition({ top: rect.bottom + 4, left: Math.max(8, rect.left - 100) });
  }, [open, anchorRef]);

  // Focus input on open
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
      // Load recent docs as default suggestions
      getRecentDocuments(8).then(setResults).catch(() => {});
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    // Delay listener to avoid immediate close from the button click that opened us
    const id = setTimeout(() => window.addEventListener('mousedown', handleClick), 0);
    return () => { clearTimeout(id); window.removeEventListener('mousedown', handleClick); };
  }, [open, onClose]);

  // Debounced search
  useEffect(() => {
    if (!open) return;
    if (!query || query.length < 2) {
      // Show recent docs when query is cleared
      if (!query) getRecentDocuments(8).then(setResults).catch(() => {});
      return;
    }
    setLoading(true);
    const id = setTimeout(async () => {
      try {
        const searchResults = await searchDocuments(query, 8);
        setResults(searchResults);
        setSelectedIndex(0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);
    return () => clearTimeout(id);
  }, [query, open]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter' && results.length > 0) {
      e.preventDefault();
      onSelect(results[selectedIndex].title);
      onClose();
    }
  }, [results, selectedIndex, onSelect, onClose]);

  if (!open) return null;

  return (
    <div
      ref={containerRef}
      className="fixed z-[60] w-80 rounded-lg border border-border bg-popover shadow-lg"
      style={{ top: position.top, left: position.left }}
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Search className="h-4 w-4 text-muted-foreground shrink-0" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search documents to link..."
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      <div className="max-h-64 overflow-y-auto py-1">
        {loading && (
          <div className="px-3 py-4 text-center text-xs text-muted-foreground">Searching...</div>
        )}
        {!loading && results.length === 0 && query.length >= 2 && (
          <div className="px-3 py-4 text-center text-xs text-muted-foreground">No documents found</div>
        )}
        {!loading && results.map((doc, index) => (
          <button
            key={doc.id}
            type="button"
            onMouseDown={(e) => {
              e.preventDefault(); // Prevent editor blur
              onSelect(doc.title);
              onClose();
            }}
            onMouseEnter={() => setSelectedIndex(index)}
            className={`w-full text-left px-3 py-2 text-sm transition-colors ${
              index === selectedIndex
                ? 'bg-accent text-accent-foreground'
                : 'text-foreground hover:bg-accent/50'
            }`}
          >
            <div className="font-medium truncate">{doc.title}</div>
            {doc.path && (
              <div className="text-xs text-muted-foreground truncate">{doc.path}</div>
            )}
          </button>
        ))}
        {!loading && results.length > 0 && !query && (
          <div className="px-3 py-1 text-xs text-muted-foreground border-t border-border mt-1 pt-2">
            Recent documents — type to search
          </div>
        )}
      </div>
    </div>
  );
}
