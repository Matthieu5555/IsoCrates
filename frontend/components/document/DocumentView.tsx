'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Save, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { Document } from '@/types';
import { MetadataDigest } from './MetadataDigest';
import { MetadataDetails } from './MetadataDetails';
import { VersionHistory } from './VersionHistory';
import { MarkdownRenderer } from '../markdown/MarkdownRenderer';
import { MarkdownEditor } from '../editor/MarkdownEditor';
import { updateDocument, deleteDocument, getDocument, getDocumentVersions } from '@/lib/api/documents';
import { ApiError } from '@/lib/api/client';
import { ConfirmDialog } from '../tree/dialogs/ConfirmDialog';
import { buttonVariants } from '@/lib/styles/button-variants';
import { toast } from '@/lib/notifications/toast';

interface DocumentViewProps {
  document: Document;
}

export function DocumentView({ document: initialDocument }: DocumentViewProps) {
  const router = useRouter();
  const [isEditing, setIsEditing] = useState(false);
  const [content, setContent] = useState(initialDocument.content);
  const [isSaving, setIsSaving] = useState(false);
  const [document, setDocument] = useState(initialDocument);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [latestAuthor, setLatestAuthor] = useState<string>('ai');
  const [latestDate, setLatestDate] = useState<string>(initialDocument.updated_at);

  // Fetch latest version to get author info
  useEffect(() => {
    async function fetchLatestVersion() {
      try {
        const versions = await getDocumentVersions(document.id);
        if (versions.length > 0) {
          setLatestAuthor(versions[0].author_type);
          setLatestDate(versions[0].created_at);
        }
      } catch (error) {
        console.error('Failed to fetch versions:', error);
      }
    }
    fetchLatestVersion();
  }, [document.id]);

  // Lock body scroll when in full-screen edit mode
  useEffect(() => {
    if (isEditing) {
      document.title; // just a reference check — actual lock:
      const original = window.document.body.style.overflow;
      window.document.body.style.overflow = 'hidden';
      return () => { window.document.body.style.overflow = original; };
    }
  }, [isEditing]);

  // Warn on tab close / navigation when editing with unsaved changes
  useEffect(() => {
    if (!isEditing) return;
    const hasChanges = content !== document.content;
    if (!hasChanges) return;

    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isEditing, content, document.content]);

  const handleEdit = useCallback(() => {
    setIsEditing(true);
  }, []);

  const handleDocumentUpdate = useCallback((updatedDoc: Document) => {
    setDocument(updatedDoc);
  }, []);

  const handleCancel = () => {
    if (content !== document.content) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to discard them?'
      );
      if (!confirmed) return;
    }
    setContent(document.content);
    setIsEditing(false);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const updatedDoc = await updateDocument(document.id, content, undefined, document.version);
      setDocument(updatedDoc);
      setIsEditing(false);
      toast.success('Document saved', 'Your changes have been saved successfully.');
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const userDraft = content; // capture before overwrite
        const latest = await getDocument(document.id);
        setDocument(latest);
        setContent(latest.content);

        // Copy the user's draft to clipboard so they don't lose work
        try {
          await navigator.clipboard.writeText(userDraft);
          toast.error(
            'Conflict -- your draft copied to clipboard',
            'This document was modified by another user. Your in-progress edits have been copied to your clipboard. The editor now shows the latest version.'
          );
        } catch {
          console.warn('[Conflict] User draft preserved in console:', userDraft);
          toast.error(
            'Conflict detected',
            'This document was modified by another user. Your in-progress edits are in the browser console (F12). The editor now shows the latest version.'
          );
        }
      } else {
        console.error('Failed to save document:', error);
        toast.error('Failed to save document', 'An error occurred while saving. Please try again.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = () => {
    setDeleteConfirmOpen(true);
  };

  const handleDeleteConfirm = async () => {
    try {
      await deleteDocument(document.id);
      toast.success('Moved to trash', 'Document can be restored from the Trash.');
      router.push('/');
    } catch (error) {
      console.error('Failed to delete document:', error);
      toast.error('Failed to delete document', 'An error occurred. Please try again.');
    }
  };

  // Full-screen edit mode rendered via portal to escape any parent constraints
  const editOverlay = isEditing
    ? createPortal(
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          {/* Top bar: document title + save/cancel */}
          <div className="flex items-center justify-between border-b border-border px-6 py-3 bg-muted/30 shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-sm font-medium truncate text-foreground">
                Editing: {document.title}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className={`${buttonVariants.primary} flex items-center gap-2`}
              >
                <Save className="h-4 w-4" />
                {isSaving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className={`${buttonVariants.secondary} flex items-center gap-2`}
              >
                <X className="h-4 w-4" />
                Cancel
              </button>
            </div>
          </div>

          {/* Editor fills remaining space */}
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-5xl mx-auto p-4 md:p-8 h-full">
              <MarkdownEditor
                content={content}
                onChange={setContent}
                placeholder="Start writing your documentation..."
                fullScreen
              />
            </div>
          </div>
        </div>,
        window.document.body,
      )
    : null;

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-8">
      <MetadataDigest
        document={document}
        onEdit={handleEdit}
        onDelete={handleDelete}
        isEditing={isEditing}
        latestAuthor={latestAuthor}
        latestDate={latestDate}
      />

      {!isEditing && (
        <>
          {document.description && (
            <p className="text-sm text-muted-foreground italic mb-6 border-l-2 border-border pl-3">
              {document.description}
            </p>
          )}
          <MarkdownRenderer content={document.content} />
          <MetadataDetails document={document} onDocumentUpdate={handleDocumentUpdate} />
          <VersionHistory docId={document.id} />
        </>
      )}

      {editOverlay}

      <ConfirmDialog
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Document"
        message={`Are you sure you want to delete "${document.title}"? It will be moved to trash.`}
        confirmText="Delete"
        variant="danger"
      />
    </div>
  );
}
