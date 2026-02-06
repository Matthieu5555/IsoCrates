'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Link as LinkIcon } from 'lucide-react';

interface LinkInsertDialogProps {
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  open: boolean;
  onClose: () => void;
  onSubmit: (text: string, url: string) => void;
  initialText?: string;
}

/**
 * Popover for inserting a standard markdown link [text](url).
 *
 * Opens below the toolbar link button. Provides text and URL fields,
 * with the text field pre-filled from the current editor selection.
 */
export function LinkInsertDialog({ anchorRef, open, onClose, onSubmit, initialText }: LinkInsertDialogProps) {
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const urlInputRef = useRef<HTMLInputElement>(null);
  const textInputRef = useRef<HTMLInputElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPosition({ top: rect.bottom + 4, left: Math.max(8, rect.left - 100) });
  }, [open, anchorRef]);

  useEffect(() => {
    if (open) {
      setText(initialText ?? '');
      setUrl('');
      setTimeout(() => {
        if (initialText) {
          urlInputRef.current?.focus();
        } else {
          textInputRef.current?.focus();
        }
      }, 0);
    }
  }, [open, initialText]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    const id = setTimeout(() => window.addEventListener('mousedown', handleClick), 0);
    return () => { clearTimeout(id); window.removeEventListener('mousedown', handleClick); };
  }, [open, onClose]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedUrl = url.trim();
    const trimmedText = text.trim() || trimmedUrl;
    if (!trimmedUrl) return;
    onSubmit(trimmedText, trimmedUrl);
    onClose();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div
      ref={containerRef}
      className="fixed z-[60] w-80 rounded-lg border border-border bg-background shadow-lg"
      style={{ top: position.top, left: position.left }}
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <LinkIcon className="h-4 w-4 text-muted-foreground shrink-0" />
        <span className="text-sm font-medium">Insert Link</span>
      </div>
      <form onSubmit={handleSubmit} className="p-3 space-y-3">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Text</label>
          <input
            ref={textInputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Display text"
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">URL</label>
          <input
            ref={urlInputRef}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="https://..."
            className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary"
          />
        </div>
        <button
          type="submit"
          disabled={!url.trim()}
          className="w-full rounded bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Insert
        </button>
      </form>
    </div>
  );
}
