'use client';

import React, { useState } from 'react';
import { movePersonalFolder, moveDocumentRef } from '@/lib/api/personal';
import { getApiErrorMessage } from '@/lib/api/client';
import type { PersonalTreeNode } from '@/types';
import { toast } from '@/lib/notifications/toast';

export interface UsePersonalTreeDragDropReturn {
  draggedNode: PersonalTreeNode | null;
  dropTargetId: string | null;
  rootDropActive: boolean;
  moving: boolean;
  handleDragStart: (e: React.DragEvent, node: PersonalTreeNode) => void;
  handleDragOver: (e: React.DragEvent, node: PersonalTreeNode) => void;
  handleDragLeave: () => void;
  handleDrop: (e: React.DragEvent, targetNode: PersonalTreeNode) => Promise<void>;
  handleDragEnd: () => void;
  handleRootDragOver: (e: React.DragEvent) => void;
  handleRootDragLeave: (e: React.DragEvent) => void;
  handleRootDrop: (e: React.DragEvent) => Promise<void>;
}

interface UsePersonalTreeDragDropOptions {
  onTreeChanged: () => Promise<void>;
  setExpandedNodes: React.Dispatch<React.SetStateAction<Set<string>>>;
}

function isAncestor(potentialParent: PersonalTreeNode, nodeId: string): boolean {
  if (!potentialParent.children) return false;
  for (const child of potentialParent.children) {
    if (child.id === nodeId) return true;
    if (isAncestor(child, nodeId)) return true;
  }
  return false;
}

function validateDrop(
  dragged: PersonalTreeNode,
  target: PersonalTreeNode,
): { valid: boolean; reason?: string } {
  if (dragged.id === target.id) {
    return { valid: false, reason: "Can't drop on itself" };
  }
  if (target.type !== 'folder') {
    return { valid: false, reason: 'Can only drop into folders' };
  }
  if (dragged.type === 'folder' && isAncestor(dragged, target.id)) {
    return { valid: false, reason: "Can't drop folder into its subfolder" };
  }
  return { valid: true };
}

export function usePersonalTreeDragDrop({
  onTreeChanged,
  setExpandedNodes,
}: UsePersonalTreeDragDropOptions): UsePersonalTreeDragDropReturn {
  const [draggedNode, setDraggedNode] = useState<PersonalTreeNode | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [rootDropActive, setRootDropActive] = useState(false);
  const [moving, setMoving] = useState(false);

  function handleDragStart(e: React.DragEvent, node: PersonalTreeNode) {
    setDraggedNode(node);
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDragOver(e: React.DragEvent, node: PersonalTreeNode) {
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
    // Only folders can be dropped at root level
    if (draggedNode.type !== 'folder') return;
    if (dropTargetId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setRootDropActive(true);
  }

  function handleRootDragLeave(e: React.DragEvent) {
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

    if (!draggedNode || draggedNode.type !== 'folder') {
      setDraggedNode(null);
      return;
    }

    const folderId = draggedNode.folder_id;
    if (!folderId) {
      setDraggedNode(null);
      return;
    }

    setMoving(true);
    try {
      await movePersonalFolder(folderId, null);
      toast.success('Moved', 'Folder moved to root');
      await onTreeChanged();
    } catch (err) {
      toast.error('Move failed', getApiErrorMessage(err));
    } finally {
      setMoving(false);
      setDraggedNode(null);
    }
  }

  async function handleDrop(e: React.DragEvent, targetNode: PersonalTreeNode) {
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

    const targetFolderId = targetNode.folder_id || targetNode.id;

    setMoving(true);
    try {
      if (draggedNode.type === 'document' && draggedNode.ref_id) {
        await moveDocumentRef(draggedNode.ref_id, targetFolderId);
        toast.success('Moved', 'Document reference moved');
      } else if (draggedNode.type === 'folder' && draggedNode.folder_id) {
        await movePersonalFolder(draggedNode.folder_id, targetFolderId);
        toast.success('Moved', 'Folder moved');
      }
      await onTreeChanged();
      setExpandedNodes(prev => new Set([...Array.from(prev), targetNode.id]));
    } catch (err) {
      toast.error('Move failed', getApiErrorMessage(err));
    } finally {
      setMoving(false);
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
    moving,
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
