'use client';

import React, { useState } from 'react';
import { Folder, FolderOpen } from 'lucide-react';
import type { TreeNode } from '@/types';
import { dialogVariants, buttonVariants } from '@/lib/styles/button-variants';

interface FolderPickerDialogProps {
  open: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  tree: TreeNode[];
}

/**
 * Dialog for selecting a target folder for batch move operations.
 *
 * Renders the folder hierarchy from the tree data and lets the user
 * click a folder to select it as the move target.
 */
export function FolderPickerDialog({ open, onClose, onSelect, tree }: FolderPickerDialogProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!open) return null;

  function toggleExpand(id: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function renderFolder(node: TreeNode, level: number): React.ReactNode {
    if (node.type !== 'folder') return null;
    const isExpanded = expanded.has(node.id);
    const indent = level * 16;
    const folders = (node.children || []).filter(c => c.type === 'folder');

    return (
      <div key={node.id}>
        <div className="flex items-center">
          <button
            onClick={() => toggleExpand(node.id)}
            className="p-1 text-xs text-muted-foreground"
            style={{ marginLeft: `${indent}px` }}
          >
            {folders.length > 0 ? (isExpanded ? '\u25BC' : '\u25B6') : '\u00A0\u00A0'}
          </button>
          <button
            onClick={() => onSelect(node.path || '')}
            className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-accent text-sm flex-1"
          >
            {isExpanded ? (
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Folder className="h-4 w-4 text-muted-foreground" />
            )}
            <span>{node.name}</span>
          </button>
        </div>
        {isExpanded && folders.map(child => renderFolder(child, level + 1))}
      </div>
    );
  }

  return (
    <div className={dialogVariants.overlay} onClick={onClose}>
      <div className={`${dialogVariants.container} max-w-md`} onClick={e => e.stopPropagation()}>
        <div className={dialogVariants.content}>
          <div className={dialogVariants.header}>
            <h2 className="text-sm font-medium">Move to folder</h2>
          </div>
          <div className={`${dialogVariants.body} max-h-80 overflow-y-auto`}>
            <button
              onClick={() => onSelect('')}
              className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-accent text-sm w-full"
            >
              <Folder className="h-4 w-4 text-muted-foreground" />
              <span className="italic">Root level</span>
            </button>
            {tree.map(node => renderFolder(node, 0))}
          </div>
          <div className={dialogVariants.footer}>
            <button onClick={onClose} className={buttonVariants.secondary}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
