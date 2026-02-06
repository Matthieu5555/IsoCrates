'use client';

import { useEffect, useState, useCallback } from 'react';
import { Trash2, RotateCcw, XCircle, CheckSquare, Square, MinusSquare } from 'lucide-react';
import { getTrash, restoreDocument, permanentDeleteDocument } from '@/lib/api/documents';
import { toast } from '@/lib/notifications/toast';
import type { DocumentListItem } from '@/types';
import { useUIStore } from '@/lib/store/uiStore';

/**
 * Trash view showing soft-deleted documents with restore and permanent delete actions.
 *
 * Accessible via the Trash node in the document tree sidebar.
 * Renders an empty state when no documents are in the trash.
 */
export default function TrashPage() {
  const [items, setItems] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [processing, setProcessing] = useState(false);

  const loadTrash = useCallback(async () => {
    try {
      const data = await getTrash();
      setItems(data);
    } catch {
      toast.error('Error', 'Failed to load trash');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTrash();
  }, [loadTrash]);

  const toggleSelect = (docId: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map(d => d.id)));
    }
  };

  const updateItemsAndTrashCount = (remaining: DocumentListItem[]) => {
    setItems(remaining);
    useUIStore.getState().setTrashCount(remaining.length);
  };

  const handleRestore = async (docId: string) => {
    try {
      await restoreDocument(docId);
      const next = items.filter(d => d.id !== docId);
      updateItemsAndTrashCount(next);
      setSelected(prev => { const n = new Set(prev); n.delete(docId); return n; });
      toast.success('Restored', 'Document restored from trash');
    } catch {
      toast.error('Error', 'Failed to restore document');
    }
  };

  const handlePermanentDelete = async (docId: string, title: string) => {
    if (!confirm(`Permanently delete "${title}"? This cannot be undone.`)) return;
    try {
      await permanentDeleteDocument(docId);
      const next = items.filter(d => d.id !== docId);
      updateItemsAndTrashCount(next);
      setSelected(prev => { const n = new Set(prev); n.delete(docId); return n; });
      toast.success('Deleted', 'Document permanently deleted');
    } catch {
      toast.error('Error', 'Failed to delete document');
    }
  };

  const executeBulkOperation = async (
    apiCall: (docId: string) => Promise<unknown>,
    successLabel: string,
    successVerb: string,
    failureVerb: string,
  ) => {
    if (selected.size === 0) return;
    setProcessing(true);
    let succeeded = 0;
    let failed = 0;
    const processed = new Set<string>();
    for (const docId of Array.from(selected)) {
      try {
        await apiCall(docId);
        processed.add(docId);
        succeeded++;
      } catch {
        failed++;
      }
    }
    const next = items.filter(d => !processed.has(d.id));
    updateItemsAndTrashCount(next);
    setSelected(prev => {
      const n = new Set(prev);
      processed.forEach(id => n.delete(id));
      return n;
    });
    toast.success(successLabel, `${succeeded} document(s) ${successVerb}`);
    if (failed > 0) toast.warning('Partial failure', `${failed} document(s) failed to ${failureVerb}`);
    setProcessing(false);
  };

  const handleBulkRestore = () =>
    executeBulkOperation(restoreDocument, 'Restored', 'restored', 'restore');

  const handleBulkPermanentDelete = async () => {
    if (selected.size === 0) return;
    if (!confirm(`Permanently delete ${selected.size} document(s)? This cannot be undone.`)) return;
    await executeBulkOperation(permanentDeleteDocument, 'Deleted', 'permanently deleted', 'delete');
  };

  if (loading) {
    return (
      <div className="p-8 text-muted-foreground">Loading trash...</div>
    );
  }

  const allSelected = items.length > 0 && selected.size === items.length;
  const someSelected = selected.size > 0 && selected.size < items.length;

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center gap-2 mb-6">
        <Trash2 className="w-6 h-6 text-muted-foreground" />
        <h1 className="text-2xl font-bold">Trash</h1>
        <span className="text-sm text-muted-foreground ml-2">
          {items.length} {items.length === 1 ? 'document' : 'documents'}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="text-muted-foreground">Trash is empty.</p>
      ) : (
        <>
          {/* Select all header + bulk actions */}
          <div className="flex items-center gap-3 mb-3 px-3 py-2 rounded-lg border border-border bg-muted/30">
            <button
              onClick={toggleSelectAll}
              className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
              title={allSelected ? 'Deselect all' : 'Select all'}
            >
              {allSelected ? (
                <CheckSquare className="w-5 h-5" />
              ) : someSelected ? (
                <MinusSquare className="w-5 h-5" />
              ) : (
                <Square className="w-5 h-5" />
              )}
            </button>
            <span className="text-sm text-muted-foreground">
              {selected.size > 0 ? `${selected.size} selected` : 'Select all'}
            </span>
            {selected.size > 0 && (
              <>
                <div className="flex-1" />
                <button
                  onClick={handleBulkRestore}
                  disabled={processing}
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  <RotateCcw className="w-4 h-4" />
                  Restore selected
                </button>
                <button
                  onClick={handleBulkPermanentDelete}
                  disabled={processing}
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded hover:bg-destructive/10 text-destructive disabled:opacity-50"
                >
                  <XCircle className="w-4 h-4" />
                  Delete selected
                </button>
              </>
            )}
          </div>

          <div className="space-y-2">
            {items.map(doc => (
              <div
                key={doc.id}
                className={`flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 cursor-pointer ${
                  selected.has(doc.id) ? 'border-primary/50 bg-primary/5' : 'border-border'
                }`}
                onClick={() => toggleSelect(doc.id)}
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className="shrink-0 text-muted-foreground">
                    {selected.has(doc.id) ? (
                      <CheckSquare className="w-5 h-5 text-primary" />
                    ) : (
                      <Square className="w-5 h-5" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium truncate">{doc.title}</div>
                    <div className="text-sm text-muted-foreground truncate">
                      {doc.path}
                      {doc.deleted_at && (
                        <span className="ml-2">
                          — deleted {new Date(doc.deleted_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1 ml-4 shrink-0" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={() => handleRestore(doc.id)}
                    className="p-2 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                    title="Restore"
                  >
                    <RotateCcw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handlePermanentDelete(doc.id, doc.title)}
                    className="p-2 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                    title="Delete permanently"
                  >
                    <XCircle className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
