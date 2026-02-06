'use client';

import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ExternalLink, Focus, CircleOff } from 'lucide-react';
import { contextMenuVariants, menuItemVariants } from '@/lib/styles/button-variants';

interface GraphNodeContextMenuProps {
  x: number;
  y: number;
  nodeId: string;
  isFocused: boolean;
  onClose: () => void;
  onOpenDocument: () => void;
  onToggleFocus: () => void;
}

export function GraphNodeContextMenu({
  x,
  y,
  isFocused,
  onClose,
  onOpenDocument,
  onToggleFocus,
}: GraphNodeContextMenuProps) {
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

  // Viewport clamping
  const menuWidth = 180;
  const menuHeight = 96;
  const clampedX = Math.min(x, window.innerWidth - menuWidth - 8);
  const clampedY = Math.min(y, window.innerHeight - menuHeight - 8);

  return createPortal(
    <div
      ref={menuRef}
      className={contextMenuVariants.container}
      style={{ left: clampedX, top: clampedY }}
    >
      <button
        onClick={() => {
          onOpenDocument();
          onClose();
        }}
        className={menuItemVariants.default}
      >
        <ExternalLink className="h-4 w-4" />
        Open Document
      </button>
      <div className={contextMenuVariants.divider} />
      <button
        onClick={() => {
          onToggleFocus();
          onClose();
        }}
        className={menuItemVariants.default}
      >
        {isFocused ? (
          <>
            <CircleOff className="h-4 w-4" />
            Unfocus
          </>
        ) : (
          <>
            <Focus className="h-4 w-4" />
            Focus
          </>
        )}
      </button>
    </div>,
    document.body
  );
}
