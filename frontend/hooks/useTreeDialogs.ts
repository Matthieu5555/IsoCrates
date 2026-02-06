'use client';

import React, { useState, useCallback } from 'react';
import type { TreeNode } from '@/types';

export interface ContextMenuState {
  x: number;
  y: number;
  node: TreeNode;
}

export interface UseTreeDialogsReturn {
  contextMenu: ContextMenuState | null;
  setContextMenu: React.Dispatch<React.SetStateAction<ContextMenuState | null>>;
  newDocDialogOpen: boolean;
  setNewDocDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  newFolderDialogOpen: boolean;
  setNewFolderDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  deleteConfirmOpen: boolean;
  setDeleteConfirmOpen: React.Dispatch<React.SetStateAction<boolean>>;
  deleteFolderDialogOpen: boolean;
  setDeleteFolderDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  selectedNode: TreeNode | null;
  setSelectedNode: React.Dispatch<React.SetStateAction<TreeNode | null>>;
  defaultPath: string;
  setDefaultPath: React.Dispatch<React.SetStateAction<string>>;
  folderPickerOpen: boolean;
  setFolderPickerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  handleDeleteClick: (node: TreeNode) => void;
  handleNewDocClick: (path?: string) => void;
  handleNewFolderClick: (path?: string) => void;
  closeContextMenu: () => void;
}

/**
 * Manages all dialog and context-menu state for the document tree.
 *
 * Extracted from DocumentTree to keep the component focused on
 * rendering and orchestration rather than dialog bookkeeping.
 */
export function useTreeDialogs(): UseTreeDialogsReturn {
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [newDocDialogOpen, setNewDocDialogOpen] = useState(false);
  const [newFolderDialogOpen, setNewFolderDialogOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteFolderDialogOpen, setDeleteFolderDialogOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<TreeNode | null>(null);
  const [defaultPath, setDefaultPath] = useState('');
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);

  const handleDeleteClick = useCallback((node: TreeNode) => {
    setSelectedNode(node);
    if (node.type === 'folder') {
      setDeleteFolderDialogOpen(true);
    } else {
      setDeleteConfirmOpen(true);
    }
  }, []);

  const handleNewDocClick = useCallback((path?: string) => {
    setDefaultPath(path || '');
    setNewDocDialogOpen(true);
  }, []);

  const handleNewFolderClick = useCallback((path?: string) => {
    setDefaultPath(path || '');
    setNewFolderDialogOpen(true);
  }, []);

  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  return {
    contextMenu,
    setContextMenu,
    newDocDialogOpen,
    setNewDocDialogOpen,
    newFolderDialogOpen,
    setNewFolderDialogOpen,
    deleteConfirmOpen,
    setDeleteConfirmOpen,
    deleteFolderDialogOpen,
    setDeleteFolderDialogOpen,
    selectedNode,
    setSelectedNode,
    defaultPath,
    setDefaultPath,
    folderPickerOpen,
    setFolderPickerOpen,
    handleDeleteClick,
    handleNewDocClick,
    handleNewFolderClick,
    closeContextMenu,
  };
}
