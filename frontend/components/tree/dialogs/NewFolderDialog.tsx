'use client';

import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { buttonVariants, dialogVariants, inputVariants } from '@/lib/styles/button-variants';
import { toast } from '@/lib/notifications/toast';

interface NewFolderDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (folderData: { path: string; description?: string }) => void;
  defaultPath?: string;
}

export function NewFolderDialog({
  open,
  onClose,
  onSubmit,
  defaultPath = '',
}: NewFolderDialogProps) {
  const [path, setPath] = useState(defaultPath);
  const [description, setDescription] = useState('');

  useEffect(() => {
    setPath(defaultPath);
  }, [defaultPath, open]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedPath = path.trim().replace(/^\/|\/$/g, '');

    if (!trimmedPath) {
      toast.error('Path required', 'Please enter a folder path');
      return;
    }

    onSubmit({
      path: trimmedPath,
      description: description || undefined,
    });

    setPath('');
    setDescription('');
  };

  if (!open) return null;

  return createPortal(
    <div className={dialogVariants.overlay} onClick={onClose}>
      <div className={`${dialogVariants.container} max-w-md`} onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit} className={dialogVariants.content}>
          <div className={dialogVariants.header}>
            <h2 className={dialogVariants.title}>New Folder</h2>
            <button type="button" onClick={onClose} className={buttonVariants.icon}>
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className={dialogVariants.body}>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Path
                </label>
                <input
                  type="text"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  className={inputVariants.default}
                  placeholder="e.g., backend/api/endpoints"
                  required
                  autoFocus
                />
                <p className="text-xs text-muted-foreground mt-2">
                  Full path including project. Use / for nesting.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Description (optional)
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className={inputVariants.default}
                  placeholder="Brief description of this folder's purpose"
                  rows={3}
                />
              </div>
            </div>
          </div>

          <div className={dialogVariants.footer}>
            <button type="button" onClick={onClose} className={buttonVariants.secondary}>
              Cancel
            </button>
            <button type="submit" className={buttonVariants.primary}>
              Create Folder
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}
