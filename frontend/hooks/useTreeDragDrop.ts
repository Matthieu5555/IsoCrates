'use client';

import React, { useState } from 'react';
import { moveFolder, moveDocument } from '@/lib/api/documents';
import { getApiErrorMessage } from '@/lib/api/client';
import type { TreeNode } from '@/types';
import { toast } from '@/lib/notifications/toast';

export interface UseTreeDragDropReturn {
  draggedNode: TreeNode | null;
  dropTargetId: string | null;
  rootDropActive: boolean;
  movingFolder: boolean;
  handleDragStart: (e: React.DragEvent, node: TreeNode) => void;
  handleDragOver: (e: React.DragEvent, node: TreeNode) => void;
  handleDragLeave: () => void;
  handleDrop: (e: React.DragEvent, targetNode: TreeNode) => Promise<void>;
  handleDragEnd: () => void;
  handleRootDragOver: (e: React.DragEvent) => void;
  handleRootDragLeave: (e: React.DragEvent) => void;
  handleRootDrop: (e: React.DragEvent) => Promise<void>;
}

interface UseTreeDragDropOptions {
  onTreeChanged: () => Promise<void>;
  setExpandedNodes: React.Dispatch<React.SetStateAction<Set<string>>>;
}

function isAncestor(potentialParent: TreeNode, node: TreeNode): boolean {
  if (!potentialParent.children) return false;
  for (const child of potentialParent.children) {
    if (child.id === node.id) return true;
    if (isAncestor(child, node)) return true;
  }
  return false;
}

function validateDrop(dragged: TreeNode, target: TreeNode): { valid: boolean; reason?: string } {
  if (dragged.id === target.id) {
    return { valid: false, reason: "Can't drop on itself" };
  }
  if (target.type !== 'folder') {
    return { valid: false, reason: 'Can only drop into folders' };
  }
  if (isAncestor(dragged, target)) {
    return { valid: false, reason: "Can't drop folder into its subfolder" };
  }
  return { valid: true };
}

export function useTreeDragDrop({ onTreeChanged, setExpandedNodes }: UseTreeDragDropOptions): UseTreeDragDropReturn {
  const [draggedNode, setDraggedNode] = useState<TreeNode | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [rootDropActive, setRootDropActive] = useState(false);
  const [movingFolder, setMovingFolder] = useState(false);

  function handleDragStart(e: React.DragEvent, node: TreeNode) {
    setDraggedNode(node);
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDragOver(e: React.DragEvent, node: TreeNode) {
    if (!draggedNode) return;
    const validation = validateDrop(draggedNode, node);
    if (validation.valid) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setDropTargetId(node.id);
      setRootDropActive(false);
    } else {
      e.dataTransfer.dropEffect = 'none';
    }
  }

  function handleDragLeave() {
    setDropTargetId(null);
  }

  function handleRootDragOver(e: React.DragEvent) {
    if (!draggedNode) return;
    // Only activate if not hovering over a specific node
    if (dropTargetId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setRootDropActive(true);
  }

  function handleRootDragLeave(e: React.DragEvent) {
    // Only deactivate if leaving the container entirely
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const { clientX, clientY } = e;
    if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
      setRootDropActive(false);
    }
  }

  async function handleRootDrop(e: React.DragEvent) {
    e.preventDefault();
    setRootDropActive(false);
    setDropTargetId(null);

    if (!draggedNode) return;

    const sourcePath = draggedNode.path || '';
    const itemName = sourcePath.split('/').filter(p => p).pop() || draggedNode.name;

    // Already at root level
    if (!sourcePath.includes('/') && draggedNode.type === 'folder') {
      setDraggedNode(null);
      return;
    }

    setMovingFolder(true);
    try {
      if (draggedNode.type === 'document') {
        // Move document to root (empty path means top-level)
        await moveDocument(draggedNode.id, '');
        toast.success('Moved', `Document moved to root`);
      } else {
        // Move folder to root level — target path is just the folder name
        await moveFolder(sourcePath, itemName);
        toast.success('Moved', `Folder moved to root`);
      }
      await onTreeChanged();
    } catch (err) {
      toast.error('Move failed', getApiErrorMessage(err));
    } finally {
      setMovingFolder(false);
      setDraggedNode(null);
    }
  }

  async function handleDrop(e: React.DragEvent, targetNode: TreeNode) {
    e.preventDefault();
    e.stopPropagation();
    setDropTargetId(null);
    setRootDropActive(false);

    if (!draggedNode) return;

    const validation = validateDrop(draggedNode, targetNode);
    if (!validation.valid) {
      toast.warning('Cannot drop here', validation.reason || 'Invalid drop target');
      setDraggedNode(null);
      return;
    }

    setMovingFolder(true);
    try {
      if (draggedNode.type === 'document') {
        // Move document into target folder
        const targetPath = targetNode.path || '';
        await moveDocument(draggedNode.id, targetPath);
        toast.success('Moved', 'Document moved');
      } else {
        // Move folder into target folder
        const sourcePath = draggedNode.path || '';
        const folderName = sourcePath.split('/').filter(p => p).pop() || draggedNode.name;
        const targetPath = targetNode.path
          ? `${targetNode.path}/${folderName}`
          : folderName;

        if (sourcePath === targetPath) {
          setDraggedNode(null);
          setMovingFolder(false);
          return;
        }

        const result = await moveFolder(sourcePath, targetPath);
        toast.success('Moved', `${result.affected_documents} document(s) updated`);
      }

      await onTreeChanged();

      if (targetNode.type === 'folder') {
        setExpandedNodes(prev => new Set([...Array.from(prev), targetNode.id]));
      }
    } catch (err) {
      toast.error('Move failed', getApiErrorMessage(err));
    } finally {
      setMovingFolder(false);
      setDraggedNode(null);
    }
  }

  function handleDragEnd() {
    setDraggedNode(null);
    setDropTargetId(null);
    setRootDropActive(false);
  }

  return {
    draggedNode,
    dropTargetId,
    rootDropActive,
    movingFolder,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragEnd,
    handleRootDragOver,
    handleRootDragLeave,
    handleRootDrop,
  };
}
