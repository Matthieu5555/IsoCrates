'use client';

import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Search, X, Plus } from 'lucide-react';
import { searchDocuments } from '@/lib/api/documents';
import { addDocumentRef } from '@/lib/api/personal';
import type { DocumentListItem } from '@/types';
import { dialogVariants, buttonVariants, inputVariants } from '@/lib/styles/button-variants';
import { toast } from '@/lib/notifications/toast';
import { getApiErrorMessage } from '@/lib/api/client';

interface AddDocumentDialogProps {
  open: boolean;
  onClose: () => void;
  targetFolderId: string;
  targetFolderName: string;
  onAdded: () => void;
}

export function AddDocumentDialog({
  open,
  onClose,
  targetFolderId,
  targetFolderName,
  onAdded,
}: AddDocumentDialogProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<DocumentListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const docs = await searchDocuments(query, 20);
        setResults(docs);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  async function handleAdd(doc: DocumentListItem) {
    setAdding(doc.id);
    try {
      await addDocumentRef(targetFolderId, doc.id);
      toast.success('Added', `"${doc.title}" added to ${targetFolderName}`);
      onAdded();
    } catch (err) {
      toast.error('Failed to add', getApiErrorMessage(err));
    } finally {
      setAdding(null);
    }
  }

  if (!open) return null;

  return createPortal(
    <div className={dialogVariants.overlay} onClick={onClose}>
      <div className={`${dialogVariants.container} max-w-lg`}>
        <div className={dialogVariants.content} onClick={(e) => e.stopPropagation()}>
          <div className={dialogVariants.header}>
            <h2 className={dialogVariants.title}>Add Document</h2>
            <button onClick={onClose} className={buttonVariants.icon}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="px-6 py-4 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search org documents..."
                className={`${inputVariants.search} pl-10`}
              />
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Adding to: <span className="font-medium">{targetFolderName}</span>
            </p>
          </div>

          <div className={dialogVariants.body}>
            {searching && (
              <div className="text-sm text-muted-foreground text-center py-4">Searching...</div>
            )}
            {!searching && query && results.length === 0 && (
              <div className="text-sm text-muted-foreground text-center py-4">No documents found</div>
            )}
            {!searching && !query && (
              <div className="text-sm text-muted-foreground text-center py-4">
                Type to search org documents
              </div>
            )}
            {results.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between px-3 py-2.5 hover:bg-muted/50 rounded transition-colors"
              >
                <div className="flex-1 min-w-0 mr-3">
                  <div className="text-sm font-medium truncate">{doc.title}</div>
                  {doc.path && (
                    <div className="text-xs text-muted-foreground truncate">{doc.path}</div>
                  )}
                </div>
                <button
                  onClick={() => handleAdd(doc)}
                  disabled={adding === doc.id}
                  className={`${buttonVariants.iconSmall} flex items-center gap-1 text-xs shrink-0`}
                >
                  <Plus className="h-3 w-3" />
                  {adding === doc.id ? '...' : 'Add'}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
