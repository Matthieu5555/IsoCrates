'use client';

import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { buttonVariants, dialogVariants, inputVariants } from '@/lib/styles/button-variants';

interface NewDocumentDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: {
    path: string;
    title: string;
    content: string;
  }) => void;
  defaultPath?: string;
}

export function NewDocumentDialog({
  open,
  onClose,
  onSubmit,
  defaultPath = '',
}: NewDocumentDialogProps) {
  const [title, setTitle] = useState('');
  const [path, setPath] = useState(defaultPath);
  const [content, setContent] = useState('# New Document\n\nStart writing here...');

  useEffect(() => {
    setPath(defaultPath);
  }, [defaultPath, open]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      title,
      path,
      content,
    });
    setTitle('');
    setPath(defaultPath);
    setContent('# New Document\n\nStart writing here...');
  };

  if (!open) return null;

  return createPortal(
    <div className={dialogVariants.overlay} onClick={onClose}>
      <div className={`${dialogVariants.container} max-w-2xl`} onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit} className={dialogVariants.content}>
          <div className={dialogVariants.header}>
            <h2 className={dialogVariants.title}>New Document</h2>
            <button type="button" onClick={onClose} className={buttonVariants.icon}>
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className={`${dialogVariants.body} space-y-6`}>
            <div>
              <label className="block text-sm font-medium mb-3">
                Path
              </label>
              <input
                type="text"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                className={inputVariants.default}
                placeholder="e.g., backend/api or frontend/components"
              />
              <p className="text-xs text-muted-foreground mt-2.5">
                Where in the tree this document lives. First segment is the project/crate.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">
                Title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className={inputVariants.default}
                placeholder="e.g., Getting Started, API Reference"
                required
                autoFocus
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-3">
                Initial Content
              </label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className={`${inputVariants.textarea} h-48 font-mono text-sm`}
                required
              />
            </div>
          </div>

          <div className={dialogVariants.footer}>
            <button type="button" onClick={onClose} className={buttonVariants.secondary}>
              Cancel
            </button>
            <button type="submit" className={buttonVariants.primary}>
              Create Document
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}
