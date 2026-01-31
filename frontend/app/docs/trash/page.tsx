'use client';

import { useEffect, useState, useCallback } from 'react';
import { Trash2, RotateCcw, XCircle } from 'lucide-react';
import { getTrash, restoreDocument, permanentDeleteDocument } from '@/lib/api/documents';
import { toast } from '@/lib/notifications/toast';
import type { DocumentListItem } from '@/types';

/**
 * Trash view showing soft-deleted documents with restore and permanent delete actions.
 *
 * Accessible via the Trash node in the document tree sidebar.
 * Renders an empty state when no documents are in the trash.
 */
export default function TrashPage() {
  const [items, setItems] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);

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

  const handleRestore = async (docId: string) => {
    try {
      await restoreDocument(docId);
      setItems(prev => prev.filter(d => d.id !== docId));
      toast.success('Restored', 'Document restored from trash');
    } catch {
      toast.error('Error', 'Failed to restore document');
    }
  };

  const handlePermanentDelete = async (docId: string, title: string) => {
    if (!confirm(`Permanently delete "${title}"? This cannot be undone.`)) return;
    try {
      await permanentDeleteDocument(docId);
      setItems(prev => prev.filter(d => d.id !== docId));
      toast.success('Deleted', 'Document permanently deleted');
    } catch {
      toast.error('Error', 'Failed to delete document');
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-muted-foreground">Loading trash...</div>
    );
  }

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
        <div className="space-y-2">
          {items.map(doc => (
            <div
              key={doc.id}
              className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-muted/50"
            >
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
              <div className="flex items-center gap-1 ml-4 shrink-0">
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
      )}
    </div>
  );
}
