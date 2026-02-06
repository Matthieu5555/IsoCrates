'use client';

import React, { useState, useCallback } from 'react';
import type { TreeNode } from '@/types';

export interface UseTreeSelectionReturn {
  selectedIds: Set<string>;
  setSelectedIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  handleSelect: (node: TreeNode, e?: React.MouseEvent) => 'selected' | 'navigated';
  clearSelection: () => void;
}

/**
 * Manages multi-select state for tree document nodes.
 *
 * - Ctrl/Cmd+click toggles individual document selection
 * - Plain click on a document clears the selection (caller should navigate)
 * - Plain click on a folder is ignored (caller should toggle expand)
 *
 * Returns 'selected' when the click was consumed by selection logic,
 * or 'navigated' when the caller should handle navigation/toggle.
 */
export function useTreeSelection(): UseTreeSelectionReturn {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const handleSelect = useCallback((node: TreeNode, e?: React.MouseEvent): 'selected' | 'navigated' => {
    // Ctrl/Cmd+click toggles selection for documents
    if (e && (e.ctrlKey || e.metaKey) && node.type === 'document') {
      setSelectedIds(prev => {
        const next = new Set(prev);
        if (next.has(node.id)) next.delete(node.id);
        else next.add(node.id);
        return next;
      });
      return 'selected';
    }

    // Plain click on a document: clear selection, let caller navigate
    if (node.type === 'document') {
      if (selectedIds.size > 0) {
        setSelectedIds(new Set());
      }
      return 'navigated';
    }

    // Folder click: let caller handle toggle
    return 'navigated';
  }, [selectedIds.size]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  return {
    selectedIds,
    setSelectedIds,
    handleSelect,
    clearSelection,
  };
}
