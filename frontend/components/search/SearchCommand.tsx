'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { Search, X, Clock, Filter } from 'lucide-react';
import { searchDocuments, getRecentDocuments, type SearchResult, type SearchFilters } from '@/lib/api/documents';
import type { DocumentListItem } from '@/types';
import { dialogVariants, buttonVariants, badgeVariants, listVariants, kbdVariants } from '@/lib/styles/button-variants';
import { getApiErrorMessage } from '@/lib/api/client';
import { toast } from '@/lib/notifications/toast';
import { SEARCH_DEBOUNCE_MS } from '@/lib/config/constants';

interface SearchCommandProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DATE_RANGES = [
  { label: 'Any time', value: '' },
  { label: 'Last 7 days', value: '7' },
  { label: 'Last 30 days', value: '30' },
  { label: 'Last 90 days', value: '90' },
] as const;

export function SearchCommand({ open, onOpenChange }: SearchCommandProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<(SearchResult | DocumentListItem)[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const [recentDocs, setRecentDocs] = useState<DocumentListItem[]>([]);

  // Filter state
  const [pathPrefix, setPathPrefix] = useState('');
  const [keywords, setKeywords] = useState('');
  const [dateRange, setDateRange] = useState('');

  // Load recent docs when modal opens with no query
  useEffect(() => {
    if (open && !query) {
      getRecentDocuments(10).then(setRecentDocs).catch(() => {});
    }
  }, [open, query]);

  // Debounced search
  useEffect(() => {
    if (!query || query.length < 2) {
      setResults([]);
      return;
    }

    const timeoutId = setTimeout(async () => {
      setLoading(true);
      try {
        const filters: SearchFilters = {};
        if (pathPrefix) filters.path_prefix = pathPrefix;
        if (keywords) filters.keywords = keywords;
        if (dateRange) {
          const d = new Date();
          d.setDate(d.getDate() - parseInt(dateRange));
          filters.date_from = d.toISOString();
        }
        const searchResults = await searchDocuments(query, 10, filters);
        setResults(searchResults);
        setSelectedIndex(0);
      } catch (error) {
        console.error('Search failed:', error);
        const message = getApiErrorMessage(error);
        toast.error('Search Failed', message);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(timeoutId);
  }, [query, pathPrefix, keywords, dateRange]);

  const handleSelect = useCallback((docId: string) => {
    router.push(`/docs/${docId}`);
    onOpenChange(false);
    setQuery('');
    setResults([]);
  }, [router, onOpenChange]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
      setShowFilters(false);
    }
  }, [open]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;

    const displayItems = query.length >= 2 ? results : recentDocs;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onOpenChange(false);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, displayItems.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && displayItems.length > 0) {
        e.preventDefault();
        handleSelect(displayItems[selectedIndex].id);
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, results, recentDocs, selectedIndex, handleSelect, onOpenChange, query]);

  if (!open) return null;

  const displayItems = query.length >= 2 ? results : recentDocs;
  const showRecent = !query && recentDocs.length > 0;

  return createPortal(
    <div className={dialogVariants.overlay} onClick={() => onOpenChange(false)}>
      <div
        className={`${dialogVariants.container} max-w-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={dialogVariants.content}>
          {/* Header with search input */}
          <div className={dialogVariants.header}>
            <div className="flex items-center gap-3 flex-1">
              <Search className="h-5 w-5 text-muted-foreground shrink-0" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search documentation..."
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                autoFocus
              />
            </div>
            <button
              type="button"
              onClick={() => setShowFilters(!showFilters)}
              className={`${buttonVariants.icon} ${showFilters ? 'text-primary' : ''}`}
              title="Toggle filters"
            >
              <Filter className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => onOpenChange(false)} className={buttonVariants.icon}>
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Filter bar */}
          {showFilters && (
            <div className="px-4 py-2 border-b border-border flex items-center gap-3 flex-wrap">
              <input
                value={pathPrefix}
                onChange={(e) => setPathPrefix(e.target.value)}
                placeholder="Filter by path..."
                className="text-xs bg-muted px-2 py-1 rounded border border-border outline-none w-40"
              />
              <input
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="Filter by keywords..."
                className="text-xs bg-muted px-2 py-1 rounded border border-border outline-none w-40"
              />
              <select
                value={dateRange}
                onChange={(e) => setDateRange(e.target.value)}
                className="text-xs bg-muted px-2 py-1 rounded border border-border outline-none"
              >
                {DATE_RANGES.map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
              {(pathPrefix || keywords || dateRange) && (
                <button
                  onClick={() => { setPathPrefix(''); setKeywords(''); setDateRange(''); }}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}

          {/* Results body */}
          <div className={dialogVariants.body}>
            {loading && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Searching...
              </div>
            )}

            {!loading && query.length > 0 && query.length < 2 && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Type at least 2 characters to search
              </div>
            )}

            {!loading && query.length >= 2 && results.length === 0 && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                No results found for &quot;{query}&quot;
              </div>
            )}

            {/* Recent docs when no query */}
            {showRecent && (
              <>
                <div className="px-3 py-2 text-xs text-muted-foreground flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  Recent documents
                </div>
                <div className={listVariants.container}>
                  {recentDocs.map((doc, index) => (
                    <button
                      key={doc.id}
                      onClick={() => handleSelect(doc.id)}
                      className={`${listVariants.item} w-full text-left flex items-center gap-3 ${
                        index === selectedIndex ? 'bg-accent text-accent-foreground' : ''
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-medium truncate text-sm">{doc.title}</div>
                        <p className="text-xs text-muted-foreground">{doc.path}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </>
            )}

            {/* Search results */}
            {!loading && results.length > 0 && (
              <div className={listVariants.container}>
                {results.map((doc, index) => {
                  const snippet = 'snippet' in doc ? doc.snippet : null;
                  return (
                    <button
                      key={doc.id}
                      onClick={() => handleSelect(doc.id)}
                      className={`${listVariants.item} w-full text-left flex items-center gap-3 ${
                        index === selectedIndex ? 'bg-accent text-accent-foreground' : ''
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <span className="font-medium truncate text-sm">
                            {doc.title || doc.repo_name}
                          </span>
                          {doc.doc_type && (
                            <span className={badgeVariants.default}>
                              {doc.doc_type}
                            </span>
                          )}
                        </div>
                        {doc.description ? (
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {doc.description}
                          </p>
                        ) : snippet ? (
                          <p
                            className="text-xs text-muted-foreground line-clamp-2"
                            dangerouslySetInnerHTML={{ __html: snippet.replace(/<(?!\/?mark\b)[^>]*>/gi, '') }}
                          />
                        ) : doc.content_preview ? (
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {doc.content_preview.replace(/[*#_`]/g, '').substring(0, 150)}...
                          </p>
                        ) : null}
                        {doc.path && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {doc.path}
                          </p>
                        )}
                      </div>
                      <svg
                        className="ml-2 h-4 w-4 opacity-50 shrink-0"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        viewBox="0 0 24 24"
                      >
                        <polyline points="9 18 15 12 9 6" />
                      </svg>
                    </button>
                  );
                })}
              </div>
            )}

            {!query && recentDocs.length === 0 && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Start typing to search documentation
              </div>
            )}
          </div>

          {/* Footer with keyboard hints */}
          <div className={dialogVariants.footer}>
            <div className="flex items-center gap-4 text-xs text-muted-foreground w-full">
              <div className="flex items-center gap-1.5">
                <kbd className={kbdVariants.default}>
                  ↑↓
                </kbd>
                <span>Navigate</span>
              </div>
              <div className="flex items-center gap-1.5">
                <kbd className={kbdVariants.default}>
                  ↵
                </kbd>
                <span>Select</span>
              </div>
              <div className="flex items-center gap-1.5">
                <kbd className={kbdVariants.default}>
                  ESC
                </kbd>
                <span>Close</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
