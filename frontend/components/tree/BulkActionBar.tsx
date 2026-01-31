'use client';

import React, { useState } from 'react';
import { Trash2, FolderInput, Tag, X } from 'lucide-react';
import { executeBatch } from '@/lib/api/documents';
import { toast } from '@/lib/notifications/toast';

interface BulkActionBarProps {
  selectedIds: Set<string>;
  onClearSelection: () => void;
  onComplete: () => void;
  onPickFolder: () => void;
}

/**
 * Floating action bar shown when multiple documents are selected in the tree.
 *
 * Provides batch delete, move, and keyword operations. All operations delegate
 * to the single POST /api/docs/batch endpoint and report partial failures
 * via toast notifications.
 */
export function BulkActionBar({ selectedIds, onClearSelection, onComplete, onPickFolder }: BulkActionBarProps) {
  const [processing, setProcessing] = useState(false);
  const count = selectedIds.size;

  if (count === 0) return null;

  const handleBatchDelete = async () => {
    if (!confirm(`Move ${count} document(s) to trash?`)) return;
    setProcessing(true);
    try {
      const result = await executeBatch('delete', Array.from(selectedIds));
      toast.success('Moved to trash', `${result.succeeded} of ${result.total} document(s) moved to trash`);
      if (result.failed > 0) {
        toast.warning('Partial failure', `${result.failed} document(s) failed`);
      }
      onClearSelection();
      onComplete();
    } catch {
      toast.error('Batch delete failed', 'An unexpected error occurred');
    } finally {
      setProcessing(false);
    }
  };

  const handleBatchKeywords = async () => {
    const input = prompt('Enter keywords to add (comma-separated):');
    if (!input) return;
    const keywords = input.split(',').map(k => k.trim()).filter(Boolean);
    if (keywords.length === 0) return;

    setProcessing(true);
    try {
      const result = await executeBatch('add_keywords', Array.from(selectedIds), { keywords });
      toast.success('Keywords added', `Updated ${result.succeeded} document(s)`);
      onClearSelection();
      onComplete();
    } catch {
      toast.error('Batch keyword update failed', 'An unexpected error occurred');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="absolute bottom-4 left-4 right-4 bg-background border border-border rounded-lg shadow-lg px-4 py-3 flex items-center gap-3 z-10">
      <span className="text-sm font-medium">{count} selected</span>
      <div className="flex-1" />
      <button
        onClick={handleBatchDelete}
        disabled={processing}
        className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded hover:bg-destructive/10 text-destructive disabled:opacity-50"
        title="Move to trash"
      >
        <Trash2 className="h-4 w-4" />
        Delete
      </button>
      <button
        onClick={onPickFolder}
        disabled={processing}
        className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded hover:bg-accent disabled:opacity-50"
        title="Move to folder"
      >
        <FolderInput className="h-4 w-4" />
        Move
      </button>
      <button
        onClick={handleBatchKeywords}
        disabled={processing}
        className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded hover:bg-accent disabled:opacity-50"
        title="Add keywords"
      >
        <Tag className="h-4 w-4" />
        Keywords
      </button>
      <button
        onClick={onClearSelection}
        className="p-1.5 rounded hover:bg-muted text-muted-foreground"
        title="Clear selection"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
