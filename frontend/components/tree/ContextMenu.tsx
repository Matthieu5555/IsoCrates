'use client';

import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Trash2, FileText, Folder } from 'lucide-react';
import { contextMenuVariants, menuItemVariants } from '@/lib/styles/button-variants';

interface ContextMenuProps {
  x: number;
  y: number;
  onClose: () => void;
  nodeType: 'document' | 'folder';
  onDelete: () => void;
  onNewDocument: () => void;
  onNewFolder: () => void;
}

export function ContextMenu({
  x,
  y,
  onClose,
  nodeType,
  onDelete,
  onNewDocument,
  onNewFolder,
}: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  const menuWidth = 180;
  const menuHeight = nodeType === 'folder' ? 160 : 48;
  const clampedX = Math.min(x, window.innerWidth - menuWidth - 8);
  const clampedY = Math.min(y, window.innerHeight - menuHeight - 8);

  return createPortal(
    <div
      ref={menuRef}
      className={contextMenuVariants.container}
      style={{ left: clampedX, top: clampedY }}
    >
      {nodeType === 'folder' && (
        <>
          <button
            onClick={() => {
              onNewDocument();
              onClose();
            }}
            className={menuItemVariants.default}
          >
            <FileText className="h-4 w-4" />
            New Document
          </button>
          <button
            onClick={() => {
              onNewFolder();
              onClose();
            }}
            className={menuItemVariants.default}
          >
            <Folder className="h-4 w-4" />
            New Folder
          </button>
          <div className={contextMenuVariants.divider} />
        </>
      )}
      <button
        onClick={() => {
          onDelete();
          onClose();
        }}
        className={menuItemVariants.danger}
      >
        <Trash2 className="h-4 w-4" />
        <span className="font-medium">Delete</span>
      </button>
    </div>,
    document.body
  );
}
