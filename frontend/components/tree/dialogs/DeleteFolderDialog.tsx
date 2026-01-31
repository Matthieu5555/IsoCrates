'use client';

import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X, ArrowUp, Trash2 } from 'lucide-react';
import { buttonVariants, dialogVariants } from '@/lib/styles/button-variants';
import type { TreeNode } from '@/types';

interface DeleteFolderDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (action: 'move_up' | 'delete_all') => void;
  folder: TreeNode | null;
  documentCount: number;
}

export function DeleteFolderDialog({
  open,
  onClose,
  onConfirm,
  folder,
  documentCount,
}: DeleteFolderDialogProps) {
  const [action, setAction] = useState<'move_up' | 'delete_all'>('move_up');

  if (!open || !folder) return null;

  const handleConfirm = () => {
    onConfirm(action);
    onClose();
  };

  return createPortal(
    <div className={dialogVariants.overlay} onClick={onClose}>
      <div className={`${dialogVariants.container} max-w-lg`} onClick={(e) => e.stopPropagation()}>
        <div className={dialogVariants.content}>
          {/* Header */}
          <div className={dialogVariants.header}>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
              <h2 className={dialogVariants.title}>Delete Folder: {folder.name}</h2>
            </div>
            <button onClick={onClose} className={buttonVariants.icon}>
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className={dialogVariants.body}>
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                This folder contains <strong>{documentCount} document(s)</strong>.
                Choose what to do with the contents:
              </p>

              {/* Action selection */}
              <div className="space-y-3">
                {/* Move Up Option */}
                <label
                  className={`flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-colors ${
                    action === 'move_up'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/50'
                  }`}
                >
                  <input
                    type="radio"
                    name="delete-action"
                    value="move_up"
                    checked={action === 'move_up'}
                    onChange={() => setAction('move_up')}
                    className="mt-1"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2 font-medium text-sm mb-1">
                      <ArrowUp className="h-4 w-4" />
                      Move contents up (Recommended)
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Delete the folder but keep all documents. Documents will move to the parent folder.
                      This preserves your content.
                    </p>
                  </div>
                </label>

                {/* Delete All Option */}
                <label
                  className={`flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-colors ${
                    action === 'delete_all'
                      ? 'border-red-500 bg-red-500/5'
                      : 'border-border hover:border-red-500/50'
                  }`}
                >
                  <input
                    type="radio"
                    name="delete-action"
                    value="delete_all"
                    checked={action === 'delete_all'}
                    onChange={() => setAction('delete_all')}
                    className="mt-1"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2 font-medium text-sm mb-1 text-red-600 dark:text-red-400">
                      <Trash2 className="h-4 w-4" />
                      Delete everything
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Permanently delete the folder and all {documentCount} document(s) inside.
                      <strong> This cannot be undone.</strong>
                    </p>
                  </div>
                </label>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className={dialogVariants.footer}>
            <button onClick={onClose} className={buttonVariants.secondary}>
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              className={action === 'delete_all' ? buttonVariants.danger : buttonVariants.primary}
            >
              {action === 'move_up' ? 'Move Contents Up' : 'Delete Everything'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
